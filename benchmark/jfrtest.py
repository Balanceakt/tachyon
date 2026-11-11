#!/usr/bin/env python3
"""Profilt Spigot und Tachyon (gleicher Kern, nacheinander) mit Java Flight Recorder waehrend des Chunk-Tests."""
import subprocess
import time
from pathlib import Path

import investigate as inv
import lowres as lr

CORE = [4]
JFR = str(Path(lr.JAVA).with_name("jfr.exe" if lr.JAVA.endswith(".exe") else "jfr"))


def main():
    jars = dict(lr.SERVERS)
    for i, name in enumerate(("Spigot", "Tachyon")):
        base = lr.prepare_base(name, jars[name], f"JFR-{name}", 25580 + i, CORE)
        lr.reset(base)
        rec = base / "rec.jfr"
        cmd = [lr.JAVA, "-Xms512M", "-Xmx512M", "-XX:ActiveProcessorCount=1",
               f"-XX:StartFlightRecording=filename={rec},settings=profile,dumponexit=true", *lr.COMMON, "-jar", "server.jar", "nogui"]
        r = inv.WRun(name, base, cmd, cpus=CORE)
        r.wait_for(lr.DONE_RE.search, 600)
        time.sleep(10)
        try:
            s = r.bench("chunks 5", "chunks", 600)["seconds"]
            lr.log(f"[{name}] 121 Chunks in {s:.1f} s (mit JFR)")
        finally:
            r.stop()
        time.sleep(3)
        for view in ("hot-methods", "thread-cpu-load"):
            out = subprocess.run([JFR, "view", "--width", "200", view, str(rec)], capture_output=True, text=True, errors="replace").stdout
            (base / f"{view}.txt").write_text(out, encoding="utf-8")
            print(f"\n===== {name}: {view} =====")
            print("\n".join(out.splitlines()[:28]))


if __name__ == "__main__":
    main()
