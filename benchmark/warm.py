#!/usr/bin/env python3
"""
Fairer "warmer" Vergleich: Erst 121 Chunks generieren (JIT-Compiler warm wie auf einem laufenden Server),
dann eine Welt erstellen und den Haenger messen. Dazu der Chunk-Test kalt (direkt nach dem Start).
  1 Kern / 512 MB: Spigot und Tachyon parallel auf getrennten P-Kernen
  ganzer PC / 8 GB: nacheinander, mit denselben Produktions-Flags wie im Maximal-Test
"""
import json
import threading
import time

import investigate as inv
import lowres as lr

RESULTS = {}


def measure(name, jar, tag, port, cpus, ram, extra=()):
    base = lr.prepare_base(name, jar, tag, port, cpus)
    lr.reset(base)
    cpu_flag = [f"-XX:ActiveProcessorCount={len(cpus)}"] if cpus else []
    cmd = [lr.JAVA, f"-Xms{ram}M", f"-Xmx{ram}M", *cpu_flag, *extra, *lr.COMMON, "-jar", "server.jar", "nogui"]
    r = inv.WRun(name, base, cmd, cpus=cpus)
    r.wait_for(lr.DONE_RE.search, 600)
    time.sleep(10)
    res = {}
    try:
        res["chunks_cold_s"] = r.bench("chunks 5", "chunks", 900)["seconds"]
        time.sleep(3)
        cw = r.bench("createworld warm_world", "createworld", 900)
        res["create_warm_freeze_ms"], res["create_warm_ready_ms"] = cw["freeze_ms"], cw["ready_ms"]
    finally:
        r.stop()
    RESULTS[tag] = res
    lr.log(f"[{tag}] Chunks kalt {res['chunks_cold_s']:.1f} s, Welt erstellen warm: Haenger {res['create_warm_freeze_ms']:.0f} ms")


def main():
    jars = dict(lr.SERVERS)
    threads = [threading.Thread(target=measure, args=("Spigot", jars["Spigot"], "Warm-Spigot-1k", 25550, [4], 512)),
               threading.Thread(target=measure, args=("Tachyon", jars["Tachyon"], "Warm-Tachyon-1k", 25551, [6], 512))]
    for t in threads:
        t.start()
        time.sleep(2)
    for t in threads:
        t.join()
    for name, port in (("Spigot", 25552), ("Tachyon", 25553)):
        measure(name, jars[name], f"Warm-{name}-max", port, None, lr.MAX_RAM, lr.MAX_FLAGS)
    out = lr.HERE / "ergebnisse" / f"warm-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")
    print("\nRESULTATE", json.dumps(RESULTS, indent=1))


if __name__ == "__main__":
    main()
