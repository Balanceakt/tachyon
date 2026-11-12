#!/usr/bin/env python3
"""
Low-Resource-Test: Wie wenig Leistung reicht Spigot bzw. Tachyon noch?

Beide Server laufen nacheinander auf genau EINEM CPU-Kern (Prozess-Affinitaet + Java wird
1 Kern gemeldet) mit immer weniger RAM. Gleiche JVM-Einstellungen fuer beide (JVM-Standard,
kein AOT-Cache, keine Tuning-Flags) - verglichen wird nur der Server-Code.

Pro RAM-Stufe:
  * startet er? Startzeit bis "Done"
  * Leerlauf: TPS / MSPT
  * Welt erstellen: laengster Server-Haenger
  * 121 neue Chunks generieren (wie Spieler, die erkunden): Dauer, TPS, laengster Haenger
  * RAM (Heap nach GC, Prozess gesamt)

Benutzung:  python lowres.py            (alle Stufen)
            python lowres.py --ram 512 256 128
"""
import argparse
import json
import ctypes
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
JAVA = str(Path(os.environ["JAVA_HOME"]) / "bin" / "java") if os.environ.get("JAVA_HOME") else (shutil.which("java") or "java")
PORT = 25590
# Parallele Testlaeufe, jeder auf eigenen physischen P-Kernen (logische CPU 2k = erster Thread von P-Kern k).
# P-Kern 0 und 1 bleiben frei fuer Windows und laufende Server.
WORKERS = [
    ("Spigot", [4]), ("Tachyon", [6]),            # je 1 Kern
    ("Spigot", [8, 10]), ("Tachyon", [12, 14]),   # je 2 Kerne
]
# Maximal-Test: jeder Server nacheinander mit dem ganzen PC, gleiche Produktions-Flags fuer beide (ohne AOT)
MAX_RAM = 8192
MAX_FLAGS = ["-XX:+UseG1GC", "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC",
             "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20",
             "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4", "-XX:InitiatingHeapOccupancyPercent=15",
             "-XX:G1MixedGCLiveThresholdPercent=90", "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32",
             "-XX:+PerfDisableSharedMem", "-XX:MaxTenuringThreshold=1", "-XX:+UseCompactObjectHeaders"]
MAX_CHUNK_RADIUS = 12  # 25x25 = 625 neue Chunks
# Szenario "schwache Hardware": je 1 Effizienz-Kern (E-Kerne = logische CPU 16-19 beim i7-12700KF)
WORKERS_E = [("Spigot", [16]), ("Tachyon", [17])]
# 3-Kern-Test: Spigot auf P-Kernen 2-4, Tachyon auf 5-7
WORKERS_3 = [("Spigot", [4, 6, 8]), ("Tachyon", [10, 12, 14])]
# Nachtest Tachyon (neuer Build) in allen Szenarien gleichzeitig: (Name, Kerne, Kern-Art)
WORKERS_RETEST = [("Tachyon", [4], "P"), ("Tachyon", [6, 8], "P"), ("Tachyon", [10, 12, 14], "P"), ("Tachyon", [16], "E")]
RAM_STEPS = [96, 128, 160, 192, 256, 384, 512, 1024]  # aufsteigend: vom kleinsten an
MAX_OK = 3  # pro Server nach 3 erfolgreichen Stufen aufhoeren
SERVERS = [("Spigot", ROOT / "Spigot-Original" / "spigot-26.3.jar"), ("Tachyon", ROOT / "Tachyon" / "tachyon-26.3.jar")]
PROPS = "level-seed=tachyon-benchmark\nonline-mode=false\nserver-port={port}\nview-distance=10\nsimulation-distance=10\nspawn-protection=0\n"
COMMON = ["--enable-native-access=ALL-UNNAMED", "--sun-misc-unsafe-memory-access=allow",
          "-Dtachyon.language=de", "-Dtachyon.verboseStartup=true"]
DONE_RE = re.compile(r"Done \((\d+[.,]\d+)s\)!")
RESULT_RE = re.compile(r"\[BENCH\] RESULT (\w+) (.*)")
SNAP = ["world", "world_nether", "world_the_end", "tachyon.yml"]

if os.name == "nt":
    os.system("")


def log(msg):
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


class Run:
    def __init__(self, name, cwd, cmd, cpus):
        self.name = name
        self.lines = queue.Queue()
        self.oom = False
        self.proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1)
        if cpus and os.name == "nt":
            mask = sum(1 << c for c in cpus)
            ok = ctypes.windll.kernel32.SetProcessAffinityMask(int(self.proc._handle), mask)
            if not ok:
                log(f"  [{name}] WARNUNG: Prozess-Affinitaet konnte nicht gesetzt werden")
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            line = line.rstrip()
            if "OutOfMemoryError" in line:
                self.oom = True
            self.lines.put(line)
        self.lines.put(None)

    def wait_for(self, pred, timeout):
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.lines.get(timeout=0.5)
            except queue.Empty:
                if self.oom:
                    raise RuntimeError("OutOfMemoryError")
                continue
            if line is None:
                raise RuntimeError("OutOfMemoryError" if self.oom else "Server beendet/abgestuerzt")
            if self.oom:
                raise RuntimeError("OutOfMemoryError")
            m = pred(line)
            if m:
                return m
        raise TimeoutError(f"Zeitlimit {timeout}s")

    def send(self, cmd):
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def bench(self, cmd, name, timeout):
        self.send("bench " + cmd)
        m = self.wait_for(lambda l: (r := RESULT_RE.search(l)) and r.group(1) == name and r, timeout)
        return {k: float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v for k, v in (kv.split("=", 1) for kv in m.group(2).split())}

    def rss_mb(self):
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {self.proc.pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace").stdout
            kb = re.sub(r"\D", "", out.strip().split('","')[-1])
            return int(kb) / 1024 if kb else None
        except Exception:
            return None

    def stop(self):
        if self.proc.poll() is None:
            try:
                self.send("stop")
                self.proc.wait(180)
            except Exception:
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)


def prepare_base(name, jar, tag, port, cpus):
    base = HERE / "run" / "lowres" / tag
    if base.exists():
        shutil.rmtree(base)
    (base / "plugins").mkdir(parents=True)
    shutil.copy2(jar, base / "server.jar")
    shutil.copy2(HERE / "bench-plugin" / "TachyonBench.jar", base / "plugins" / "TachyonBench.jar")
    (base / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (base / "server.properties").write_text(PROPS.format(port=port), encoding="utf-8")
    log(f"[{tag}] Vorbereitung: Welt einmal erzeugen...")
    r = Run(tag, base, [JAVA, "-Xmx2G", *COMMON, "-jar", "server.jar", "nogui"], cpus=cpus)
    r.wait_for(DONE_RE.search, 600)
    time.sleep(10)
    # Fair: Tachyons Spawnsuche im Hintergrund muss fertig sein, bevor die Testwelt gespeichert wird.
    # Sonst setzt Tachyon sie in jedem Testlauf fort und waermt dabei den JIT-Compiler vor (verfaelscht Chunk-Tests).
    cfg = base / "tachyon.yml"
    waited = 0
    while cfg.exists() and "pending-spawn" in cfg.read_text(encoding="utf-8", errors="replace") and waited < 180:
        time.sleep(2)
        waited += 2
    if waited:
        log(f"[{tag}] Spawnsuche im Hintergrund nach weiteren {waited} s abgeschlossen")
    r.stop()
    snap = base / "_snapshot"
    snap.mkdir()
    for item in SNAP:
        src = base / item
        if src.is_dir():
            shutil.copytree(src, snap / item)
        elif src.is_file():
            shutil.copy2(src, snap / item)
    return base


def reset(base):
    for item in SNAP + ["lr_world", "logs", "crash-reports"]:
        p = base / item
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file():
            p.unlink()
    snap = base / "_snapshot"
    for item in SNAP:
        src = snap / item
        if src.is_dir():
            shutil.copytree(src, base / item)
        elif src.is_file():
            shutil.copy2(src, base / item)


def run_step(tag, base, ram, cpus, extra=(), chunk_radius=5):
    name = tag
    reset(base)
    res = {"ram": ram}
    cpu_flag = [f"-XX:ActiveProcessorCount={len(cpus)}"] if cpus else []
    cmd = [JAVA, f"-Xms{ram}M", f"-Xmx{ram}M", *cpu_flag, *extra, *COMMON, "-jar", "server.jar", "nogui"]
    res["cmd"] = " ".join(c for c in cmd if not c.startswith(str(Path.home())))
    t0 = time.perf_counter()
    r = Run(name, base, cmd, cpus=cpus)
    try:
        r.wait_for(DONE_RE.search, 600)
        res["start_s"] = time.perf_counter() - t0
        log(f"  [{name} {ram} MB] gestartet in {res['start_s']:.1f} s")
        time.sleep(10)
        idle = r.bench("idle 10", "idle", 120)
        res["idle_tps"], res["idle_mspt"] = idle["tps"], idle["mspt"]
        cw = r.bench("createworld lr_world", "createworld", 400)
        res["create_freeze_ms"], res["create_ready_ms"], res["create_tps"] = cw["freeze_ms"], cw["ready_ms"], cw["tps"]
        log(f"  [{name} {ram} MB] Welt erstellt: Haenger {cw['freeze_ms']:.0f} ms, TPS {cw['tps']:.1f}")
        ch = r.bench(f"chunks {chunk_radius}", "chunks", 900)
        res["chunks_s"], res["chunks_tps"], res["chunks_freeze_ms"] = ch["seconds"], ch["tps"], ch["freeze_ms"]
        res["chunks_done"] = f"{int(ch['loaded'])}/{int(ch['total'])}"
        log(f"  [{name} {ram} MB] {int(ch['total'])} Chunks: {ch['seconds']:.1f} s")
        mem = r.bench("mem", "mem", 60)
        res["heap_mb"] = mem["heap_used_mb"]
        res["rss_mb"] = r.rss_mb()
        res["status"] = "ok"
    except Exception as e:
        res["status"] = "OOM" if (r.oom or "OutOfMemory" in str(e)) else f"FEHLER: {e}"
        log(f"  [{name} {ram} MB] {res['status']}")
    finally:
        r.stop()
    return res


def fmt(v, unit="", digits=1):
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    return f"{v:,.{digits}f}{unit}".replace(",", "X").replace(".", ",").replace("X", ".")


def worker(index, name, jar, cpus, steps, results, kind="P", port_base=PORT):
    tag = f"{name}-{len(cpus)}{kind}"
    port = port_base + index
    try:
        base = prepare_base(name, jar, tag, port, cpus)
    except Exception as e:
        log(f"[{tag}] Vorbereitung fehlgeschlagen: {e}")
        return
    lst = results.setdefault((name, len(cpus), kind), [])
    for ram in steps:
        log(f"[{tag}] Stufe: {ram} MB RAM, {len(cpus)} Kern(e)")
        res = run_step(tag, base, ram, cpus)
        lst.append(res)
        if sum(1 for r in lst if r["status"] == "ok") >= MAX_OK:
            log(f"[{tag}] {MAX_OK} Stufen laufen stabil - fertig")
            break


def system_info():
    info = {}
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name; "
                              "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)"],
                             capture_output=True, text=True).stdout.strip().splitlines()
        info["cpu"] = out[0].strip()
        info["ram_gb"] = out[1].strip()
    except Exception:
        pass
    info["threads"] = os.cpu_count()
    ver = subprocess.run([JAVA, "-version"], capture_output=True, text=True).stderr.splitlines()
    info["java"] = ver[0] if ver else "?"
    return info


def run_max():
    info = system_info()
    log(f"Maximal-Test auf: {info}")
    results = []
    for i, (name, jar) in enumerate(SERVERS):
        tag = f"{name}-max"
        base = prepare_base(name, jar, tag, PORT + 20 + i, None)
        log(f"[{tag}] {MAX_RAM} MB RAM, alle {info['threads']} Threads")
        res = run_step(tag, base, MAX_RAM, None, MAX_FLAGS, MAX_CHUNK_RADIUS)
        res["server"] = name
        results.append(res)
    out = HERE / "ergebnisse"
    out.mkdir(exist_ok=True)
    stamp = f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    (out / f"lowres-max-{stamp}.json").write_text(json.dumps({"system": info, "flags": MAX_FLAGS, "ram_mb": MAX_RAM,
                                                               "chunks": (2 * MAX_CHUNK_RADIUS + 1) ** 2, "results": results}, indent=1), encoding="utf-8")
    for r in results:
        log(f"{r['server']}: {r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ram", type=int, nargs="*", default=RAM_STEPS)
    ap.add_argument("--ecores", action="store_true", help="Szenario schwache Hardware: je 1 E-Kern")
    ap.add_argument("--max", action="store_true", help="Maximal-Test: ganzer PC, 8 GB, nacheinander")
    ap.add_argument("--cores3", action="store_true", help="je 3 P-Kerne")
    ap.add_argument("--retest", action="store_true", help="Tachyon in allen Szenarien neu testen")
    args = ap.parse_args()
    if args.max:
        return run_max()
    jars = dict(SERVERS)
    results = {}
    threads = []
    workers, kind, port_base = (WORKERS_E, "E", PORT + 10) if args.ecores else (WORKERS, "P", PORT)
    if args.cores3:
        workers, kind, port_base = WORKERS_3, "P", PORT + 30
    if args.retest:
        plan = [(n, c, k, PORT + 40) for n, c, k in WORKERS_RETEST]
    else:
        plan = [(n, c, kind, port_base) for n, c in workers]
    for i, (name, cpus, knd, pbase) in enumerate(plan):
        t = threading.Thread(target=worker, args=(i, name, jars[name], cpus, args.ram, results, knd, pbase))
        t.start()
        threads.append(t)
        time.sleep(2)
    for t in threads:
        t.join()

    rows = ["| Server | Kerne | RAM | Status | Start | Leerlauf TPS / MSPT | Welt erstellen: Haenger | 121 Chunks: Dauer | ... TPS dabei | ... laengster Haenger | Heap / Prozess |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for (name, cores, kind), lst in sorted(results.items(), key=lambda kv: (kv[0][2], kv[0][1], kv[0][0])):
        for r in lst:
            rows.append(f"| {name} | {cores} {kind}-Kern | {r['ram']} MB | {r['status']} | {fmt(r.get('start_s'), ' s')} | "
                        f"{fmt(r.get('idle_tps'))} / {fmt(r.get('idle_mspt'), ' ms')} | {fmt(r.get('create_freeze_ms'), ' ms', 0)} | "
                        f"{fmt(r.get('chunks_s'), ' s')} ({r.get('chunks_done', '-')}) | {fmt(r.get('chunks_tps'))} | {fmt(r.get('chunks_freeze_ms'), ' ms', 0)} | "
                        f"{fmt(r.get('heap_mb'), ' MB', 0)} / {fmt(r.get('rss_mb'), ' MB', 0)} |")
    print("\n" + "\n".join(rows))
    out = HERE / "ergebnisse"
    out.mkdir(exist_ok=True)
    stamp = f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    suffix = "-retest" if args.retest else ("-ekern" if args.ecores else ("-3kern" if args.cores3 else ""))
    path = out / f"lowres{suffix}-{stamp}.md"
    (out / f"lowres{suffix}-{stamp}.json").write_text(json.dumps([{"server": n, "cores": c, "kind": k, **r} for (n, c, k), lst in results.items() for r in lst], indent=1), encoding="utf-8")
    path.write_text("# Low-Resource-Test (1 und 2 CPU-Kerne, RAM in Stufen, vom kleinsten an)\n\n"
                    "Gleiche JVM-Einstellungen fuer beide Server (JVM-Standard, kein AOT, keine Tuning-Flags), Prozess auf 1 Kern festgelegt.\n\n"
                    + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"\nBericht: {path}")


if __name__ == "__main__":
    main()
