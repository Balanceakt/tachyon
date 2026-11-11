#!/usr/bin/env python3
"""Erzeugt aus dem neuesten Low-Resource-Ergebnis (ergebnisse/lowres-*.json) Grafiken fuer das GitHub-README."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "ergebnisse"
BG, TEXT, MUTED = "#12131c", "#e8e9f3", "#8a8fa3"
COLORS = {"Spigot": "#8a8fa3", "Tachyon": "#7ee0c3"}
BAD = "#ff6b8b"

data = []
for pattern in ("lowres-2*.json", "lowres-3kern-*.json", "lowres-ekern-*.json"):
    files = sorted((HERE / "ergebnisse").glob(pattern))
    if files:
        for d in json.loads(files[-1].read_text(encoding="utf-8")):
            d.setdefault("kind", "P")
            data.append(d)
# Nachtest mit dem aktuellen Tachyon-Build ersetzt die alten Tachyon-Werte derselben Stufe
retest = sorted((HERE / "ergebnisse").glob("lowres-retest-*.json"))
if retest:
    for r in json.loads(retest[-1].read_text(encoding="utf-8")):
        r.setdefault("kind", "P")
        data = [d for d in data if not (d["server"] == r["server"] and d["cores"] == r["cores"] and d["kind"] == r["kind"] and d["ram"] == r["ram"])]
        data.append(r)
groups = sorted({(d["kind"], d["cores"]) for d in data}, key=lambda g: (g[0] != "P", g[1]))
rams = sorted({d["ram"] for d in data})


def group_title(kind, cores):
    if kind == "E":
        return f"{cores} E-Kern (schwache CPU)"
    return f"{cores} CPU-Kern" + ("e" if cores > 1 else "")


def get(server, group, ram):
    kind, cores = group
    for d in data:
        if d["server"] == server and d["cores"] == cores and d["kind"] == kind and d["ram"] == ram:
            return d
    return None


def chart(metric, title, unit, fname, lower_better=True, log=False):
    fig, axes = plt.subplots(1, len(groups), figsize=(6.2 * len(groups), 4.4), facecolor=BG, squeeze=False)
    for ax, cores in zip(axes[0], groups):
        ax.set_facecolor(BG)
        width = 0.38
        for i, server in enumerate(("Spigot", "Tachyon")):
            for j, ram in enumerate(rams):
                d = get(server, cores, ram)
                x = j + (i - 0.5) * width
                if d is None:
                    continue
                if d["status"] != "ok" or d.get(metric) is None:
                    ax.text(x, 0.02, "OOM" if d["status"] == "OOM" else "Absturz", transform=ax.get_xaxis_transform(),
                            ha="center", va="bottom", color=BAD, fontsize=8, fontweight="bold", rotation=90)
                    continue
                v = d[metric]
                ax.bar(x, v, width * 0.95, color=COLORS[server], label=server if j == 0 or not ax.get_legend_handles_labels()[1].count(server) else None)
                ax.text(x, v, (f"{v:,.0f}".replace(",", ".") if v >= 10 else f"{v:.1f}".replace(".", ",")), ha="center", va="bottom", color=TEXT, fontsize=8)
        ax.set_xticks(range(len(rams)))
        ax.set_xticklabels([f"{r} MB" for r in rams], color=TEXT, fontsize=9)
        ax.set_title(group_title(*cores), color=TEXT, fontsize=12, fontweight="bold")
        ax.tick_params(colors=TEXT, length=0)
        if log:
            ax.set_yscale("log")
        ax.set_ylabel(unit, color=MUTED)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#3a3d52")
        handles, labels = ax.get_legend_handles_labels()
        uniq = dict(zip(labels, handles))
        ax.legend(uniq.values(), uniq.keys(), facecolor=BG, edgecolor="#3a3d52", labelcolor=TEXT, fontsize=9)
    fig.suptitle(title + ("  -  weniger ist besser" if lower_better else "  -  mehr ist besser"), color=TEXT, fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = OUT / fname
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("Grafik:", path)


chart("create_freeze_ms", "Server-Hänger beim Erstellen einer Welt", "ms", "lowres-welt-erstellen.png", log=True)
chart("chunks_s", "Dauer: 121 neue Chunks generieren", "Sekunden", "lowres-chunks.png")

# Minimal lauffaehiger RAM je Server/Kerne
print("\nMinimum (alles bestanden):")
for g in groups:
    for server in ("Spigot", "Tachyon"):
        ok = [d["ram"] for d in data if d["server"] == server and d["cores"] == g[1] and d["kind"] == g[0] and d["status"] == "ok"]
        print(f"  {server} {group_title(*g)}: {min(ok) if ok else '-'} MB")


# ---------------------------------------------------------------- Maximal-Test
maxfiles = sorted((HERE / "ergebnisse").glob("lowres-max-*.json"))
if maxfiles:
    mx = json.loads(maxfiles[-1].read_text(encoding="utf-8"))
    res = {r["server"]: r for r in mx["results"]}
    metrics = [("start_s", "Start bis 'Done'", "s"), ("create_freeze_ms", "Hänger beim\nWelt erstellen", "ms"),
               ("chunks_s", f"{mx['chunks']} neue Chunks\ngenerieren", "s")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), facecolor=BG)
    for ax, (key, label, unit) in zip(axes, metrics):
        ax.set_facecolor(BG)
        vals = [res.get(n, {}).get(key) for n in ("Spigot", "Tachyon")]
        bars = ax.bar(["Spigot", "Tachyon"], [v or 0 for v in vals], color=[COLORS["Spigot"], COLORS["Tachyon"]], width=0.6)
        top = max(v or 0 for v in vals) or 1
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, (v or 0) + top * 0.03, "-" if v is None else (f"{v:,.0f} {unit}" if v >= 100 else f"{v:.1f} {unit}"),
                    ha="center", va="bottom", color=TEXT, fontsize=11, fontweight="bold")
        ax.set_title(label, color=TEXT, fontsize=12, fontweight="bold")
        ax.set_ylim(0, top * 1.25)
        ax.set_yticks([])
        ax.tick_params(colors=TEXT, length=0, labelsize=11)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#3a3d52")
    sysinfo = mx["system"]
    fig.suptitle(f"Maximale Leistung: {sysinfo.get('cpu', '?')}, {sysinfo.get('threads')} Threads, {mx['ram_mb'] // 1024} GB RAM je Server",
                 color=TEXT, fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUT / "max-leistung.png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("Grafik:", OUT / "max-leistung.png")
    print("\nMAX:", json.dumps({k: {m: v.get(m) for m in ("start_s", "create_freeze_ms", "chunks_s", "idle_mspt", "heap_mb", "rss_mb")} for k, v in res.items()}, indent=1))
    print("SYSTEM:", sysinfo, "FLAGS:", " ".join(mx["flags"]))

# ---------------------------------------------------------------- Tabellen fuer STATS.md
def cell(d, key, unit, digits=1):
    if d is None:
        return "–"
    if d["status"] != "ok" and d.get(key) is None:
        return "❌ OOM" if d["status"] == "OOM" else "❌"
    v = d.get(key)
    if v is None:
        return "❌"
    txt = f"{v:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{txt} {unit}"


print("\n=== TABELLEN ===")
for g in groups:
    print(f"\n### {group_title(*g)}\n")
    print("| RAM | Spigot: Welt erstellen | Tachyon: Welt erstellen | Spigot: 121 Chunks | Tachyon: 121 Chunks | Spigot: Start | Tachyon: Start |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for ram in rams:
        sp, ta = get("Spigot", g, ram), get("Tachyon", g, ram)
        if sp is None and ta is None:
            continue
        print(f"| {ram} MB | {cell(sp, 'create_freeze_ms', 'ms', 0)} | {cell(ta, 'create_freeze_ms', 'ms', 0)} | "
              f"{cell(sp, 'chunks_s', 's')} | {cell(ta, 'chunks_s', 's')} | {cell(sp, 'start_s', 's')} | {cell(ta, 'start_s', 's')} |")
