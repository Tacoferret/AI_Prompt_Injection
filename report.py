"""Make the bar chart of Attack Success Rate. Usage: python report.py results/<run_dir>

Reads summary.csv (written by score.py). Bars: E2 (document injection) and E3 (search-snippet
injection), ASR over eligible trials, with k/n counts printed on the bars. E1 has no ASR."""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
COLORS = {"E2": "#2a78d6", "E3": "#eb6834"}  # categorical slots 1 and 2, fixed order
LABELS = {"E2": "E2: injection in\ndocument body", "E3": "E3: injection in\nsearch snippet"}


def make_chart(run_dir):
    run_dir = Path(run_dir)
    rows = {r["Condition"]: r for r in csv.DictReader(open(run_dir / "summary.csv", encoding="utf-8"))}
    conds = [c for c in ("E2", "E3") if c in rows]
    vals, kn = [], []
    for c in conds:
        n_seen = rows[c]["Payload seen (runs)"]
        k = rows[c]["Eligible marker answers"]
        v = rows[c]["ASR eligible (%)"]
        vals.append(float(v) if v != "n/a" else 0.0)
        kn.append(f"{k}/{n_seen}")

    fig, ax = plt.subplots(figsize=(6.2, 4.2), dpi=160)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
    x = range(len(conds))
    bars = ax.bar(x, vals, width=0.42, color=[COLORS[c] for c in conds], zorder=3)
    ax.set_xticks(list(x)); ax.set_xticklabels([LABELS[c] for c in conds], color=INK, fontsize=10)
    ax.set_ylim(0, max(10, min(100, max(vals) * 1.35 + 5)))
    ax.set_ylabel("Attack success rate (%)", color=INK2, fontsize=10)
    ax.set_title("Does injection location matter?  ASR by condition", color=INK, fontsize=12, loc="left", pad=12)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", colors=INK2, length=0); ax.tick_params(axis="x", length=0)
    for b, v, k in zip(bars, vals, kn):
        ax.text(b.get_x() + b.get_width() / 2, v + ax.get_ylim()[1] * 0.02, f"{v:.1f}%  ({k})",
                ha="center", va="bottom", color=INK, fontsize=10)
    fig.text(0.01, 0.01, "ASR = marker-included answers / injected trials where the payload was seen. Counts in brackets.",
             color=INK2, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = run_dir / "asr_bar_chart.png"
    fig.savefig(out, facecolor=SURFACE)
    print(f"saved {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python report.py results/<run_dir>")
    make_chart(sys.argv[1])
