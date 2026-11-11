#!/usr/bin/env python3
"""
Tachyon-Benchmark: vergleicht den originalen Spigot mit Tachyon unter identischen Bedingungen.

Jeder Server bekommt einen eigenen, frischen Testordner (benchmark/run/<name>) mit
gleichem Seed, gleichen Einstellungen, gleichem RAM und dem Mess-Plugin TachyonBench.
Die Server laufen nacheinander (nie gleichzeitig), damit sie sich nicht die CPU teilen.

Gemessen wird:
  * Erster Start (kalt, inkl. Entpacken und Welt-Generierung) bis "Done"
  * Neustart (warm) bis "Done" - Durchschnitt aus mehreren Laeufen
  * Tick-Zeiten im Leerlauf (TPS / MSPT)
  * Welterstellung im laufenden Betrieb: wie lange der Server einfriert und wann die Welt bereit ist
  * RAM (Heap nach GC und Prozess-RAM)

Benutzung:
  python benchmark.py
  python benchmark.py --warm-runs 3 --verbose
  python benchmark.py --only tachyon
"""
import argparse
import datetime as dt
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_JAVA = Path(os.environ["JAVA_HOME"]) / "bin" / "java" if os.environ.get("JAVA_HOME") else Path(shutil.which("java") or "java")
PORT = 25599

SERVER_PROPERTIES = f"""level-seed=tachyon-benchmark
online-mode=false
server-port={PORT}
view-distance=10
simulation-distance=10
spawn-protection=0
motd=Tachyon Benchmark
enable-status=true
"""

DONE_RE = re.compile(r"Done \((\d+[.,]\d+)s\)!")
RESULT_RE = re.compile(r"\[BENCH\] RESULT (\w+) (.*)")

# Farben fuer die Live-Ausgabe (Windows Terminal kann ANSI)
C = {"spigot": "\033[33m", "tachyon": "\033[36m", "tachyon-aot": "\033[35m", "ok": "\033[32m", "bad": "\033[31m", "dim": "\033[90m", "b": "\033[1m", "r": "\033[0m"}
if os.name == "nt":
    os.system("")  # ANSI in der Windows-Konsole aktivieren


def log(msg, color=None):
    ts = dt.datetime.now().strftime("%H:%M:%S")
    c = C.get(color, "")
    print(f"{C['dim']}{ts}{C['r']} {c}{msg}{C['r'] if c else ''}", flush=True)


class Server:
    def __init__(self, name, jar, java, xmx, verbose, extra_jvm=None, aot=False):
        self.name = name
        self.aot = aot
        self.aot_mode = None
        self.jar = Path(jar)
        self.java = str(java)
        self.xmx = xmx
        self.verbose = verbose
        self.extra_jvm = extra_jvm or []
        self.dir = HERE / "run" / name
        self.proc = None
        self.lines = queue.Queue()

    def prepare(self):
        if self.dir.exists():
            shutil.rmtree(self.dir)
        (self.dir / "plugins").mkdir(parents=True)
        shutil.copy2(self.jar, self.dir / "server.jar")
        shutil.copy2(HERE / "bench-plugin" / "TachyonBench.jar", self.dir / "plugins" / "TachyonBench.jar")
        (self.dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        (self.dir / "server.properties").write_text(SERVER_PROPERTIES, encoding="utf-8")

    def base_cmd(self):
        # Gleiche JVM-Grundeinstellungen fuer alle Varianten, damit der Vergleich fair ist
        return [self.java, f"-Xms{self.xmx}", f"-Xmx{self.xmx}", "--enable-native-access=ALL-UNNAMED",
                "-Dtachyon.language=de", "-Dtachyon.verboseStartup=true", *self.extra_jvm]

    def extract(self):
        subprocess.run([*self.base_cmd(), "-DbundlerMainClass=", "-jar", "server.jar"], cwd=self.dir,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)

    def train_aot(self):
        """Wie start.bat ab dem 2. Start: AOT-Training, bei Fehlschlag Fallback ohne AOTClassLinking."""
        t0 = time.perf_counter()
        aot = self.dir / "tachyon.aot"
        for attempt, extra in enumerate(([], ["-XX:-AOTClassLinking"])):
            if aot.exists():
                aot.unlink()
            with open(self.dir / f"aot-training-{attempt + 1}.log", "w", encoding="utf-8", errors="replace") as out:
                subprocess.run([*self.base_cmd(), *extra, "-XX:+UnlockDiagnosticVMOptions", "-XX:+AOTStreamableObjects", "-Dtachyon.aotTraining=true", "-XX:AOTCacheOutput=tachyon.aot",
                                "@tachyon-libs/tachyon-launch.args", "nogui"], cwd=self.dir, stdin=subprocess.DEVNULL,
                               stdout=out, stderr=subprocess.STDOUT, timeout=900)
            if aot.exists() and aot.stat().st_size > 0:
                self.aot_mode = "voll" if not extra else "sicher (ohne Class-Linking)"
                return time.perf_counter() - t0
            log(f"[{self.name}] AOT-Training Versuch {attempt + 1} fehlgeschlagen", "bad")
        raise RuntimeError("AOT-Cache wurde nicht erzeugt")

    def start(self, use_cache=True):
        if self.aot:
            cache = ["-XX:AOTCache=tachyon.aot"] if use_cache and (self.dir / "tachyon.aot").exists() else []
            cmd = [*self.base_cmd(), *cache, "@tachyon-libs/tachyon-launch.args", "nogui"]
        else:
            cmd = [*self.base_cmd(), "-jar", "server.jar", "nogui"]
        self.lines = queue.Queue()
        self.proc = subprocess.Popen(cmd, cwd=self.dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            self.lines.put(line)
            interesting = ("[BENCH]" in line or "Done (" in line or "WorldManager" in line
                           or "ERROR" in line or "Exception" in line or "Can't keep up" in line)
            if self.verbose or interesting:
                log(f"[{self.name}] {line}", self.name if self.name in C else None)
        self.lines.put(None)

    def send(self, command):
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def wait_for(self, predicate, timeout):
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError(f"{self.name}: Server hat sich unerwartet beendet")
            m = predicate(line)
            if m:
                return m
        raise TimeoutError(f"{self.name}: Zeitlimit ({timeout}s) erreicht")

    def wait_done(self, timeout=900):
        t0 = time.perf_counter()
        m = self.wait_for(DONE_RE.search, timeout)
        return time.perf_counter() - t0, float(m.group(1).replace(",", "."))

    def bench(self, command, result_name, timeout=600):
        self.send(f"bench {command}")
        m = self.wait_for(lambda l: (r := RESULT_RE.search(l)) and r.group(1) == result_name and r, timeout)
        return {k: float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v
                for k, v in (kv.split("=", 1) for kv in m.group(2).split())}

    def rss_mb(self):
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {self.proc.pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, errors="replace").stdout
            kb = re.sub(r"\D", "", out.strip().split('","')[-1])
            return int(kb) / 1024 if kb else None
        except Exception:
            return None

    def stop(self, timeout=180):
        if self.proc and self.proc.poll() is None:
            self.send("stop")
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                log(f"[{self.name}] reagiert nicht auf stop - beende Prozess", "bad")
                self.proc.kill()


def run_suite(srv, warm_runs, results):
    r = results.setdefault(srv.name, {})
    srv.prepare()
    warm = []
    log(f"=== {srv.name.upper()}: frischer Testordner, erster Start (kalt) ===", "b")
    t_cold = time.perf_counter()
    if srv.aot:
        srv.extract()  # wie start.bat: Bibliotheken entpacken, dann direkt ueber den Classpath starten
    srv.start(use_cache=False)
    try:
        wall, reported = srv.wait_done()
        wall = time.perf_counter() - t_cold
        r["cold_wall_s"], r["cold_done_s"] = wall, reported
        log(f"[{srv.name}] Erster Start: {wall:.1f} s (Server meldet {reported:.1f} s)", srv.name)

        time.sleep(15)  # zur Ruhe kommen lassen (Tachyon generiert nach "Done" noch kurz im Hintergrund)
        idle = srv.bench("idle 10", "idle")
        r["idle_mspt"], r["idle_tps"] = idle["mspt"], idle["tps"]

        log(f"[{srv.name}] Erstelle Welt im laufenden Betrieb...", srv.name)
        cw = srv.bench("createworld bench_world", "createworld")
        r["create_freeze_ms"] = cw["freeze_ms"]
        r["create_blocked_ms"] = cw["blocked_call_ms"]
        r["create_ready_ms"] = cw["ready_ms"]
        r["create_tps"] = cw["tps"]

        ev = srv.bench("events 2000000", "events")
        r["event_ns"] = ev["ns_per_event"]

        time.sleep(15)
        mem = srv.bench("mem", "mem")
        r["heap_mb"] = mem["heap_used_mb"]
        r["rss_mb"] = srv.rss_mb()
    finally:
        srv.stop()

    if srv.aot:
        log(f"=== {srv.name.upper()}: einmaliges AOT-Training (wie start.bat beim 2. Start) ===", "b")
        r["aot_train_s"] = srv.train_aot()
        log(f"[{srv.name}] AOT-Training fertig nach {r['aot_train_s']:.1f} s, Modus: {srv.aot_mode}", srv.name)

    for i in range(warm_runs - len(warm)):
        log(f"=== {srv.name.upper()}: Neustart {i + 1} (warm) ===", "b")
        srv.start()
        try:
            wall, reported = srv.wait_done()
            warm.append((wall, reported))
            log(f"[{srv.name}] Neustart: {wall:.1f} s (Server meldet {reported:.1f} s)", srv.name)
        finally:
            srv.stop()
    if warm:
        r["warm_wall_s"] = sum(w for w, _ in warm) / len(warm)
        r["warm_done_s"] = sum(d for _, d in warm) / len(warm)


# (Schluessel, Beschriftung, Einheit, kleiner_ist_besser)
METRICS = [
    ("aot_train_s", "Einmaliges AOT-Training (2. Start)", "s", True),
    ("cold_wall_s", "Erster Start (bis 'Done', gemessen)", "s", True),
    ("cold_done_s", "Erster Start (vom Server gemeldet)", "s", True),
    ("warm_wall_s", "Neustart (bis 'Done', gemessen)", "s", True),
    ("warm_done_s", "Neustart (vom Server gemeldet)", "s", True),
    ("create_freeze_ms", "Welterstellung: laengster Server-Haenger", "ms", True),
    ("create_blocked_ms", "Welterstellung: Main-Thread blockiert", "ms", True),
    ("create_ready_ms", "Welterstellung: bis Welt bereit", "ms", True),
    ("create_tps", "Welterstellung: TPS waehrenddessen", "", False),
    ("event_ns", "Events: Zeit pro Event (5 Listener)", "ns", True),
    ("idle_mspt", "Leerlauf: MSPT (ms pro Tick)", "ms", True),
    ("idle_tps", "Leerlauf: TPS", "", False),
    ("heap_mb", "RAM: Heap nach GC", "MB", True),
    ("rss_mb", "RAM: Prozess gesamt", "MB", True),
]


def fmt(v, unit):
    if v is None:
        return "-"
    return f"{v:,.1f} {unit}".replace(",", "X").replace(".", ",").replace("X", ".").strip()


def compare(a, b, lower_better):
    if a is None or b is None or a == 0:
        return "-", None
    change = (a - b) / a * 100 if lower_better else (b - a) / a * 100
    if abs(change) < 2:
        return "gleich", 0
    factor = (a / b if lower_better else b / a) if b else float("inf")
    word = "besser" if change > 0 else "schlechter"
    extra = f" ({factor:.1f}x)" if change > 0 and factor >= 1.5 else ""
    return f"{abs(change):.0f} % {word}{extra}", change


NAMES = {"spigot": "Original", "tachyon": "Tachyon", "tachyon-aot": "Tachyon+AOT"}


def report(results, args):
    variants = [v for v in ("spigot", "tachyon", "tachyon-aot") if v in results]
    base = results.get("spigot", {})
    others = [v for v in variants if v != "spigot"]
    rows = []
    for key, label, unit, lower in METRICS:
        if not any(results[v].get(key) is not None for v in variants):
            continue
        vals = [fmt(results[v].get(key), unit) for v in variants]
        cmps = [compare(base.get(key), results[v].get(key), lower) for v in others]
        rows.append((label, vals, cmps))
    if not rows:
        print("Keine Ergebnisse.")
        return

    w = max(len(r[0]) for r in rows)
    head = "".join(f"{NAMES[v]:>14}  " for v in variants)
    cmp_head = "  ".join(f"{(NAMES[v] + ' vs. Original'):<28}" for v in others)
    print()
    print(f"{C['b']}{'Messung'.ljust(w)}  {head}{cmp_head}{C['r']}")
    for label, vals, cmps in rows:
        cells = "".join(f"{v:>14}  " for v in vals)
        texts = []
        for text, change in cmps:
            col = C["ok"] if change and change > 0 else C["bad"] if change and change < 0 else ""
            texts.append(f"{col}{text:<28}{C['r']}")
        print(f"{label.ljust(w)}  {cells}{'  '.join(texts)}")

    out_dir = HERE / "ergebnisse"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"benchmark-{stamp}.md"
    lines = [
        f"# Tachyon-Benchmark {dt.datetime.now():%d.%m.%Y %H:%M}",
        "",
        f"- Original: `{args.original}`",
        f"- Tachyon: `{args.tachyon}`",
        f"- Java: `{args.java}`, RAM je Server: {args.xmx}, Seed: tachyon-benchmark",
        f"- Neustarts gemittelt: {args.warm_runs}, Server liefen nacheinander (nicht gleichzeitig)",
        "",
        "| Messung | " + " | ".join(NAMES[v] for v in variants) + " | "
        + " | ".join(f"{NAMES[v]} vs. Original" for v in others) + " |",
        "|---|" + "---:|" * len(variants) + "---|" * len(others),
    ]
    for label, vals, cmps in rows:
        lines.append(f"| {label} | " + " | ".join(vals) + " | " + " | ".join(t for t, _ in cmps) + " |")
    lines += ["", "Hinweise:",
              "- Startzeiten schwanken je nach Festplatten-Cache und Hintergrundlast um einige Prozent.",
              "- 'laengster Server-Haenger' = groesster Abstand zwischen zwei Ticks (normal: 50 ms).",
              "- 'bis Welt bereit': Tachyon wartet zusaetzlich, bis der Spawnbereich (5x5 Chunks) generiert ist; "
              "der Server laeuft dabei normal weiter.",
              "- Tachyon+AOT ist derselbe Server wie Tachyon, startet aber mit Javas AOT-Cache (wie start.bat)."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nBericht gespeichert: {path}")


def main():
    ap = argparse.ArgumentParser(description="Benchmark: Original-Spigot gegen Tachyon")
    ap.add_argument("--original", default=str(ROOT / "Spigot-Original" / "spigot-26.3.jar"))
    ap.add_argument("--tachyon", default=str(ROOT / "Tachyon" / "tachyon-26.3.jar"))
    ap.add_argument("--java", default=str(DEFAULT_JAVA))
    ap.add_argument("--xmx", default="2G")
    ap.add_argument("--warm-runs", type=int, default=2)
    ap.add_argument("--only", choices=["original", "tachyon", "tachyon-aot"])
    ap.add_argument("--no-aot", action="store_true", help="Variante Tachyon+AOT auslassen")
    ap.add_argument("--verbose", action="store_true", help="komplette Server-Ausgabe anzeigen")
    args = ap.parse_args()

    for p in (args.java, args.original, args.tachyon):
        if not Path(p).exists():
            sys.exit(f"Nicht gefunden: {p}")

    results = {}
    servers = []
    if args.only in (None, "original"):
        servers.append(Server("spigot", args.original, args.java, args.xmx, args.verbose))
    if args.only in (None, "tachyon"):
        servers.append(Server("tachyon", args.tachyon, args.java, args.xmx, args.verbose))
    if args.only in (None, "tachyon-aot") and not args.no_aot:
        servers.append(Server("tachyon-aot", args.tachyon, args.java, args.xmx, args.verbose, aot=True))

    t0 = time.time()
    for srv in servers:
        try:
            run_suite(srv, args.warm_runs, results)
        except Exception as e:
            log(f"[{srv.name}] FEHLER: {e}", "bad")
            if srv.proc and srv.proc.poll() is None:
                srv.proc.kill()
    log(f"Benchmark fertig nach {(time.time() - t0) / 60:.1f} min", "b")
    report(results, args)


if __name__ == "__main__":
    main()
