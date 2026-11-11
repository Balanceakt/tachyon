#!/usr/bin/env python3
"""Gegenprobe: Spigot und Tachyon NACHEINANDER auf demselben Kern (1 Kern, 512 MB, Chunk-Test ohne Welt-Erstellen),
in beiden Reihenfolgen, damit Kern-Unterschiede und Reihenfolge-Effekte ausgeschlossen sind."""
import investigate as inv
import lowres as lr

ORDER = ["Spigot", "Tachyon", "Tachyon", "Spigot"]
CORE = [4]


def main():
    jars = dict(lr.SERVERS)
    bases = {n: lr.prepare_base(n, jars[n], f"Gleich-{n}", 25570 + i, CORE) for i, n in enumerate(("Spigot", "Tachyon"))}
    times = {"Spigot": [], "Tachyon": []}
    for name in ORDER:
        inv.CPUS[name] = CORE
        lr.reset(bases[name])
        r = inv.start(name, bases[name])
        try:
            s = r.bench("chunks 5", "chunks", 600)["seconds"]
            times[name].append(s)
            lr.log(f"[{name}] gleicher Kern {CORE}: 121 Chunks in {s:.1f} s")
        finally:
            r.stop()
    print("\n=== Gleicher Kern, nacheinander ===")
    for n, t in times.items():
        print(f"{n:8} " + "  ".join(f"{x:.1f} s" for x in t) + f"   (Mittel {sum(t) / len(t):.1f} s)")


if __name__ == "__main__":
    main()
