#!/usr/bin/env python3
"""Pareto plots from results/summary.json (BRIEF A5) -> results/plots/*.png and *.svg.

  fmax_vs_area.*     fmax at the slowest corner (max_ss_100C_1v60) vs standard-cell area,
                     every closing run, with the Pareto front (higher fmax, smaller area)
  energy_vs_delay.*  energy per operation vs clock period
  area_by_arch.*     standard-cell area per architecture, default vs preserved flow

Only summary.json is read. Colours: categorical slots 1-3 of the dataviz reference
palette (validated all-pairs, light surface); identity is also carried by marker
shape and direct labels, never by colour alone.

Run inside the iic-osic container (matplotlib) from the repo root:
    python3 scripts/plots.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
S = json.loads((REPO / "results" / "summary.json").read_text())
OUT = REPO / "results" / "plots"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
STYLE = {  # variant -> (label, colour, marker)
    "default": ("Default flow (ABC restructures)", "#2a78d6", "o"),
    "preserved": ("Structure-preserved flow", "#eb6834", "s"),
    "preserved_P1": ("Preserved + PIPE=1 (STA fix)", "#1baf7a", "D"),
}
ARCH_ORDER = ["RCA", "CLA4", "CSLA", "BK", "KS", "SK", "HC", "BEH"]
# Label offsets (points) where neighbouring labels would collide: (chart, variant, arch) -> (dx, dy).
NUDGE = {("fmax_vs_area", "default", "RCA"): (-26, -12), ("fmax_vs_area", "default", "CSLA"): (6, -12),
         ("fmax_vs_area", "preserved", "CLA4"): (-30, 6), ("fmax_vs_area", "preserved", "BK"): (6, -12),
         ("fmax_vs_area", "default", "HC"): (6, -12),
         ("energy_vs_delay", "preserved", "BK"): (-22, 6), ("energy_vs_delay", "preserved", "CLA4"): (6, -12),
         ("energy_vs_delay", "preserved", "SK"): (6, 2), ("energy_vs_delay", "default", "KS"): (-14, -14),
         ("energy_vs_delay", "default", "HC"): (4, 6), ("energy_vs_delay", "default", "CLA4"): (-10, -14),
         ("energy_vs_delay", "default", "BEH"): (6, 4), ("energy_vs_delay", "default", "RCA"): (6, -10)}


def points():
    for v, archs in S["variants"].items():
        for a, r in archs.items():
            if "area" in r and "power_annotated" in r:
                yield v, a, r


def setup(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2)


def label(ax, x, y, text, dx=6, dy=4):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=8, color=INK)


def save(fig, name):
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def scatter(name, title, xlabel, ylabel, xy, front=None):
    fig, ax = plt.subplots(figsize=(8, 5.2))
    setup(ax, title, xlabel, ylabel)
    pts = [(v, a, *xy(r)) for v, a, r in points()]
    if front:
        f = front(pts)
        ax.plot([p[2] for p in f], [p[3] for p in f], color=INK2, linewidth=1.2, linestyle="--", zorder=1,
                label="Pareto front")
    for v, (lab, col, mk) in STYLE.items():
        sel = [p for p in pts if p[0] == v]
        if not sel:
            continue
        ax.scatter([p[2] for p in sel], [p[3] for p in sel], s=56, c=col, marker=mk, edgecolors=SURFACE,
                   linewidths=2, label=lab, zorder=3)
        for p in sel:
            label(ax, p[2], p[3], p[1] + (" P1" if v == "preserved_P1" else ""), *NUDGE.get((name, v, p[1]), (6, 4)))
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="best")
    save(fig, name)


def fmax_front(pts):
    """Pareto front for (min area, max fmax): sweep by area, keep each new fmax maximum."""
    best, front = -1.0, []
    for p in sorted(pts, key=lambda p: (p[2], -p[3])):
        if p[3] > best:
            best = p[3]
            front.append(p)
    return front


def energy_front(pts):
    """Pareto front for (min period, min energy): sweep by period, keep each new energy minimum."""
    best, front = float("inf"), []
    for p in sorted(pts, key=lambda p: (p[2], p[3])):
        if p[3] < best:
            best = p[3]
            front.append(p)
    return front


def bars():
    fig, ax = plt.subplots(figsize=(8, 4.6))
    setup(ax, "Standard-cell area by architecture", "", "Standard-cell area (µm²)")
    w = 0.36
    for i, v in enumerate(("default", "preserved")):
        lab, col, _ = STYLE[v]
        xs = [k + (i - 0.5) * (w + 0.04) for k in range(len(ARCH_ORDER))]
        ys = [S["variants"][v][a]["area"]["stdcell_area_um2"] for a in ARCH_ORDER]
        ax.bar(xs, ys, width=w, color=col, label=lab, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.set_xticks(range(len(ARCH_ORDER)), ARCH_ORDER)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left")
    ax.set_ylim(0, None)
    ax.grid(False, axis="x")
    save(fig, "area_by_arch")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scatter("fmax_vs_area", "fmax at the slowest corner vs area (higher and further left is better)",
            "Standard-cell area (µm²)", "fmax at max_ss_100C_1v60 (MHz)",
            lambda r: (r["area"]["stdcell_area_um2"], r["fmax_slowest_corner_MHz"]), fmax_front)
    scatter("energy_vs_delay", "Energy per operation vs clock period (lower and further left is better)",
            "Minimum clock period T (ns)", "Energy per operation (pJ)",
            lambda r: (r["min_period_ns"], r["power_annotated"]["energy_per_op_pJ"]), energy_front)
    bars()
    print("->", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
