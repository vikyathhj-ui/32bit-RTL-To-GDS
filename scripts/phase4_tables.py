#!/usr/bin/env python3
"""Print the Phase 4 Markdown tables used in docs/ from results/summary.json.

Docs never carry hand-typed PPA numbers (BRIEF A5): tables are pasted from
this script's output, so they can be regenerated and checked at any time.

    python3 scripts/phase4_tables.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = json.loads((REPO / "results" / "summary.json").read_text())


def rows(variant: str):
    for arch, r in S["variants"][variant].items():
        if "area" in r:
            yield arch, r


def ppa(variant: str) -> str:
    out = [f"**{variant}** (from `results/summary.json`)", "",
           "| Arch | Min T (ns) | Fails at (ns) | fmax max_ss (MHz) | fmax nom_tt (MHz) | Std cells | "
           "Cell area (µm²) | Die (µm²) | Power (mW) | Energy/op (pJ) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for a, r in rows(variant):
        p = r.get("power_annotated", {})
        out.append(f"| {a} | {r['min_period_ns']} | {r['failing_neighbour_ns']} | "
                   f"{r['fmax_slowest_corner_MHz']} | {r['timing']['nom_tt_025C_1v80']['fmax_MHz']} | "
                   f"{r['area']['stdcell_count']} | {r['area']['stdcell_area_um2']:.1f} | "
                   f"{r['area']['die_area_um2']:.1f} | "
                   f"{p['total_W'] * 1e3:.3f} | {p['energy_per_op_pJ']:.2f} |" if p else "| — | — |")
    return "\n".join(out)


def paths(variant: str) -> str:
    out = [f"**{variant}**", "",
           "| Arch | Critical path at max_ss: logic cells / all cells | Post-synth delay (ns) | "
           "Post-route delay (ns) | Change | Same netlist, ideal wires (ns) | Wire delay (ns) | "
           "Repair-buffer area (µm²) | Wirelength (µm) |",
           "|---|---|---|---|---|---|---|---|---|"]
    for a, r in rows(variant):
        cp, pp, wd = r["critical_path_slowest"], r["post_synth_vs_post_route"], r["wire_delay"]
        out.append(f"| {a} | {cp['logic_depth_excluding_buffers']} / {cp['cells_on_path']} | "
                   f"{pp['post_synth_delay_ns']} | {pp['post_route_delay_ns']} | "
                   f"{pp['degradation_percent']:+}% | {wd['delay_ideal_wires_ns']} | "
                   f"{wd['wire_delay_ns']} ({wd['wire_delay_percent_of_routed']}%) | "
                   f"{r['area']['timing_repair_buffer_area_um2']:.1f} | {r['physical']['route_wirelength_um']} |")
    return "\n".join(out)


def sweep(variant: str) -> str:
    out = [f"**{variant}**", "", "| Arch | Periods tried (ns): C = closes, F = fails | Non-monotonic |",
           "|---|---|---|"]
    for a, r in S["variants"][variant].items():
        tried = ", ".join(f"{x['period_ns']}{'C' if x['status'] == 'CLOSES' else 'F'}"
                          for x in sorted(r["sweep_runs"], key=lambda x: x["period_ns"]))
        out.append(f"| {a} | {tried} | {', '.join(map(str, r['nonmonotonic_points_ns'])) or '—'} |")
    return "\n".join(out)


if __name__ == "__main__":
    for v in S["variants"]:
        print(ppa(v), "", paths(v), "", sweep(v), "", sep="\n")
