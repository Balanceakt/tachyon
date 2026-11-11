#!/usr/bin/env python3
"""
Untersuchung: Warum ist Tachyon auf 1 Kern beim Chunk-Test (121 Chunks) doppelt so schnell wie Spigot?

Hypothese: Spigot generiert beim Welt-Erstellen synchron viele Chunks (Spawnsuche). Deren Speichern/Entladen
laeuft danach auf demselben Kern und bremst den direkt folgenden Chunk-Test.

Drei Varianten je Server (1 Kern, 512 MB, beide Server parallel auf getrennten Kernen):
  A  Basis:        Start -> Chunk-Test (keine Welt erstellt)
  B  Wie Benchmark: Welt erstellen -> 3 s -> Chunk-Test  (+ Chunk-Zustand jede Sekunde)
  C  Mit Pause:    Welt erstellen -> 30 s warten -> Chunk-Test
"""
import re
import threading
import time

import lowres as lr

CPUS = {"Spigot": [4], "Tachyon": [6]}
RAM = 512
WATCH_RE = re.compile(r"\[BENCH\] WATCH t=(\d+) (.*)")
results = {}


class WRun(lr.Run):
    """Wie lr.Run, merkt sich aber alle WATCH-Zeilen (auch waehrend andere Messungen laufen)."""
    watch = None

    def _read(self):
        self.watch = []
        for line in self.proc.stdout:
            line = line.rstrip()
            m = WATCH_RE.search(line)
            if m:
                self.watch.append((int(m.group(1)), m.group(2)))
            if "OutOfMemoryError" in line:
                self.oom = True
            self.lines.put(line)
        self.lines.put(None)


def start(name, base):
    cmd = [lr.JAVA, f"-Xms{RAM}M", f"-Xmx{RAM}M", "-XX:ActiveProcessorCount=1", *lr.COMMON, "-jar", "server.jar", "nogui"]
    r = WRun(name, base, cmd, cpus=CPUS[name])
    r.wait_for(lr.DONE_RE.search, 600)
    time.sleep(10)
    return r


def collect_watch(r, timeout):
    """Wartet auf das Ende von 'bench watch' und liefert alle WATCH-Zeilen."""
    r.wait_for(lambda l: "RESULT watch" in l, timeout)
    return list(r.watch)


def run_server(name, jar, index):
    tag = f"Unters-{name}"
    base = lr.prepare_base(name, jar, tag, 25560 + index, CPUS[name])
    res = results.setdefault(name, {})

    # A: Basis
    lr.reset(base)
    r = start(name, base)
    try:
        res["A_chunks_s"] = r.bench("chunks 5", "chunks", 600)["seconds"]
        lr.log(f"[{name}] A Basis: 121 Chunks in {res['A_chunks_s']:.1f} s")
    finally:
        r.stop()

    # B: wie im Benchmark, mit Chunk-Zustand
    lr.reset(base)
    r = start(name, base)
    try:
        res["B_create_ms"] = r.bench("createworld lr_world", "createworld", 600)["freeze_ms"]
        r.watch.clear()
        r.send("bench watch 40")
        res["B_chunks_s"] = r.bench("chunks 5", "chunks", 600)["seconds"]
        res["B_watch"] = collect_watch(r, 120)
        lr.log(f"[{name}] B wie Benchmark: Welt {res['B_create_ms']:.0f} ms, danach 121 Chunks in {res['B_chunks_s']:.1f} s")
    finally:
        r.stop()

    # C: mit 30 s Pause nach dem Welt-Erstellen
    lr.reset(base)
    r = start(name, base)
    try:
        r.bench("createworld lr_world", "createworld", 600)
        r.watch.clear()
        r.send("bench watch 30")
        res["C_watch"] = collect_watch(r, 120)
        res["C_chunks_s"] = r.bench("chunks 5", "chunks", 600)["seconds"]
        lr.log(f"[{name}] C mit 30 s Pause: 121 Chunks in {res['C_chunks_s']:.1f} s")
    finally:
        r.stop()


def main():
    jars = dict(lr.SERVERS)
    threads = [threading.Thread(target=run_server, args=(n, jars[n], i)) for i, n in enumerate(("Spigot", "Tachyon"))]
    for t in threads:
        t.start()
        time.sleep(2)
    for t in threads:
        t.join()

    print("\n=== Ergebnis (1 Kern, 512 MB) ===")
    print(f"{'':28}{'Spigot':>10}{'Tachyon':>10}")
    for key, label in (("A_chunks_s", "A Basis (keine Welt)"), ("B_chunks_s", "B Welt + 3 s"), ("C_chunks_s", "C Welt + 30 s Pause")):
        print(f"{label:28}" + "".join(f"{results.get(n, {}).get(key, float('nan')):>9.1f}s" for n in ("Spigot", "Tachyon")))
    for name in ("Spigot", "Tachyon"):
        print(f"\n--- {name}: Chunk-Zustand nach dem Welt-Erstellen (voll/holder/wartet aufs Entladen/verwerfen) ---")
        for label in ("B_watch", "C_watch"):
            rows = results.get(name, {}).get(label, [])
            print(f"  {label}:")
            for t, txt in rows[:1] + rows[1:12:2] + rows[-2:]:
                print(f"    t={t:>2}s {txt}")


if __name__ == "__main__":
    main()
