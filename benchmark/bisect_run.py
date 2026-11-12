#!/usr/bin/env python3
"""Misst eine beliebige Server-Jar: 1 Kern (CPU 4), 512 MB, 121 neue Chunks, N Laeufe.
Benutzung: python bisect_run.py <jar> <label> [laeufe]"""
import sys
import time
from pathlib import Path

import investigate as inv
import lowres as lr


def main():
    jar, label = Path(sys.argv[1]), sys.argv[2]
    runs = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    inv.CPUS[label] = [4]
    base = lr.prepare_base(label, jar, f"Bisect-{label}", 25585, [4])
    times = []
    for _ in range(runs):
        lr.reset(base)
        r = inv.start(label, base)
        try:
            times.append(r.bench("chunks 5", "chunks", 600)["seconds"])
        finally:
            r.stop()
    print(f"RESULTAT {label}: " + "  ".join(f"{t:.1f} s" for t in times) + f"   Mittel {sum(times) / len(times):.1f} s", flush=True)


if __name__ == "__main__":
    main()
