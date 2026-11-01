#!/usr/bin/env python3
"""Wire contribution to the critical path of each closing run (BRIEF A4, DECISIONS D-024).

The flow's post-synthesis vs post-route comparison mixes two effects: the
resizer's upsizing/buffering (which only happens in PnR) and the real wires.
To isolate the wires, the *same* final netlist is timed twice with OpenSTA at
nom_ss_100C_1v60 (ss_100C_1v60 liberty, the flow's SDC, propagated clock):
  routed  with the nominal extracted SPEF
  ideal   without SPEF (zero wire RC; pin capacitances only)
delay = T - worst setup slack; wire delay = routed - ideal.
The routed result is cross-checked against the flow's own metrics.json value.

Run inside the iic-osic container from the repo root:
    python3 scripts/wire_delay.py      # -> sim_build/wire/<run>/wire_delay.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402

CORNER = "nom_ss_100C_1v60"
LIB = (Path(os.environ.get("PDK_ROOT", "/foss/pdks")) / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib"
       / "sky130_fd_sc_hd__ss_100C_1v60.lib")
SWEEPS = {"default": REPO / "results" / "flow" / "sweep", "preserved": REPO / "results" / "flow" / "sweep_preserved"}


def worst_slack(run: Path, work: Path, name: str, spef: bool) -> float | None:
    tcl = work / f"{name}.tcl"
    lines = [f"read_liberty {LIB}",
             f"read_verilog {run / 'final' / 'nl' / 'alu_top.nl.v'}",
             "link_design alu_top",
             f"read_sdc {run / 'final' / 'sdc' / 'alu_top.sdc'}"]
    if spef:
        lines.append(f"read_spef {run / 'final' / 'spef' / 'nom' / 'alu_top.nom.spef'}")
    lines += ["set_propagated_clock [all_clocks]",
              "puts \"WORST_SLACK [sta::format_time [sta::worst_slack_cmd max] 6]\"",
              "report_checks -path_delay max -fields {fanout cap slew} -digits 4", "exit"]
    tcl.write_text("\n".join(lines) + "\n")
    p = subprocess.run(["sta", "-no_splash", "-exit", str(tcl)], capture_output=True, text=True)
    (work / f"{name}.rpt").write_text(p.stdout + p.stderr)
    m = re.search(r"WORST_SLACK\s+([-\d.]+)", p.stdout)
    return float(m.group(1)) if m else None


def one(variant: str, arch: str) -> dict | None:
    f = SWEEPS[variant] / f"{arch}.json"
    if not f.exists():
        return None
    sweep = json.loads(f.read_text())
    if sweep.get("status") != "DONE":
        return None
    T = sweep["min_period_ns"]
    run = REPO / next(r["run_dir"] for r in sweep["runs"] if r["period_ns"] == T)
    work = REPO / "sim_build" / "wire" / run.name
    work.mkdir(parents=True, exist_ok=True)
    ws_routed = worst_slack(run, work, "routed", spef=True)
    ws_ideal = worst_slack(run, work, "ideal", spef=False)
    flow_ws = json.loads((run / "final" / "metrics.json").read_text()).get(f"timing__setup__ws__corner:{CORNER}")
    rec = {"run": str(run.relative_to(REPO)), "period_ns": T, "corner": CORNER,
           "ws_routed_ns": ws_routed, "ws_ideal_wires_ns": ws_ideal, "flow_ws_ns": flow_ws,
           "note": "same final netlist; routed = with nominal SPEF, ideal = no SPEF; delay = T - WS",
           "reports": [str((work / n).relative_to(REPO)) for n in ("routed.rpt", "ideal.rpt")]}
    if ws_routed is not None and ws_ideal is not None:
        rec["delay_routed_ns"] = round(T - ws_routed, 4)
        rec["delay_ideal_wires_ns"] = round(T - ws_ideal, 4)
        rec["wire_delay_ns"] = round(ws_ideal - ws_routed, 4)
        rec["wire_delay_percent_of_routed"] = round(100 * (ws_ideal - ws_routed) / (T - ws_routed), 1)
    (work / "wire_delay.json").write_text(json.dumps(rec, indent=2) + "\n")
    return rec


def main() -> int:
    ok = True
    for variant in SWEEPS:
        for arch in ADDERS:
            r = one(variant, arch)
            if r is None:
                continue
            ok &= r.get("wire_delay_ns") is not None
            print(f"{variant:<9} {arch:<5} T={r['period_ns']} routed={r.get('delay_routed_ns')} "
                  f"ideal={r.get('delay_ideal_wires_ns')} wire={r.get('wire_delay_ns')} "
                  f"({r.get('wire_delay_percent_of_routed')}%) ws={r['ws_routed_ns']} flow_ws={r['flow_ws_ns']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
