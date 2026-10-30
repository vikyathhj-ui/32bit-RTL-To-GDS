#!/usr/bin/env python3
"""Build results/summary.json from the sweep, flow reports, power and ABC results (BRIEF A4/A5).

summary.json is the ONLY source for every PPA number in the README, docs and
resume (BRIEF A5). This script only reads tool outputs; each value is stored
with the path of the report it came from. Small key reports are copied into
results/flow/<variant>/<ARCH>/ so they remain inspectable without runs/.

Per flow variant (default, preserved; DECISIONS D-027) and architecture, at the
minimum closing period found by scripts/sweep.py:
  - area: standard cells, standard-cell area, core and die area, utilisation
  - timing: setup/hold WNS and TNS at all 9 corners, reg-to-reg setup WS,
            fmax per corner = 1 / (T - setup WS)
  - critical path at max_ss_100C_1v60 (startpoint, endpoint, arrival, logic depth)
  - post-synthesis vs post-route delay at nom_ss_100C_1v60 (D-024)
  - signoff counts from the flow (DRC, LVS, antenna) and wirelength
  - gate-level activity-annotated power and energy/op (D-025), if measured

Run inside the iic-osic container from the repo root:
    python3 scripts/parse_flow.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402

RES = REPO / "results" / "flow"
SLOWEST = "max_ss_100C_1v60"
PRE_POST_CORNER = "nom_ss_100C_1v60"
VARIANT_DIRS = {"default": RES / "sweep", "preserved": RES / "sweep_preserved"}
OUT_PIN = re.compile(r"\s(\S+)/(X|Y|SUM|COUT)\s+\((sky130_fd_sc_hd__\w+)\)")


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def critical_path(rpt: Path) -> dict:
    """First (worst) path in an OpenSTA max.rpt for one corner."""
    text = rpt.read_text()
    parts = text.split("Startpoint:", 2)
    path = "Startpoint:" + parts[1] if len(parts) > 1 else ""
    cells = [m.group(3).replace("sky130_fd_sc_hd__", "") for m in OUT_PIN.finditer(path)]
    logic = [c for c in cells if not re.match(r"(buf|clkbuf|clkdlybuf|dlygate|dlymetal)", c)]
    sp = re.search(r"Startpoint: (\S+) \(([^)]*)\)", path)
    ep = re.search(r"Endpoint: (\S+) \(([^)]*)\)", path)
    arr = re.search(r"([-\d.]+)\s+data arrival time", path)
    return {"startpoint": sp and f"{sp.group(1)} ({sp.group(2)})",
            "endpoint": ep and f"{ep.group(1)} ({ep.group(2)})",
            "data_arrival_ns": float(arr.group(1)) if arr else None,
            "cells_on_path": len(cells), "logic_depth_excluding_buffers": len(logic),
            "cell_types": cells, "source": rel(rpt)}


def step_dir(run: Path, suffix: str) -> Path | None:
    hits = sorted(run.glob(f"*-{suffix}"), key=lambda p: int(p.name.split("-")[0]))
    return hits[-1] if hits else None


def one(variant: str, arch: str) -> dict | None:
    f = VARIANT_DIRS[variant] / f"{arch}.json"
    if not f.exists():
        return None
    sweep = json.loads(f.read_text())
    rec = {"variant": variant, "arch": arch, "sweep_status": sweep.get("status") or "RUNNING",
           "min_period_ns": sweep.get("min_period_ns"),
           "failing_neighbour_ns": sweep.get("failing_neighbour_ns"),
           "nonmonotonic_points_ns": sweep.get("nonmonotonic_points_ns", []),
           "sweep_runs": [{k: r.get(k) for k in ("period_ns", "status", "setup_ws_slowest", "hold_ws_min")}
                          for r in sweep["runs"]],
           "sweep_source": rel(f)}
    if sweep.get("status") != "DONE":
        return rec
    T = sweep["min_period_ns"]
    run = REPO / next(r["run_dir"] for r in sweep["runs"] if r["period_ns"] == T)
    m = json.loads((run / "final" / "metrics.json").read_text())
    corners = sorted(k.split("corner:")[1] for k in m if k.startswith("timing__setup__ws__corner:"))
    keep = RES / variant / arch
    keep.mkdir(parents=True, exist_ok=True)
    shutil.copy(run / "final" / "metrics.json", keep / "metrics.json")

    rec["closing_run"] = rel(run)
    rec["metrics_source"] = rel(keep / "metrics.json")
    rec["area"] = {
        "stdcell_count": m.get("design__instance__count__stdcell"),
        "stdcell_area_um2": m.get("design__instance__area__stdcell"),
        "core_area_um2": m.get("design__core__area"),
        "die_area_um2": m.get("design__die__area"),
        "utilisation": m.get("design__instance__utilization__stdcell"),
        "timing_repair_buffer_area_um2": m.get("design__instance__area__class:timing_repair_buffer"),
    }
    rec["timing"] = {c: {
        "setup_ws_ns": m.get(f"timing__setup__ws__corner:{c}"),
        "setup_tns_ns": m.get(f"timing__setup__tns__corner:{c}"),
        "hold_ws_ns": m.get(f"timing__hold__ws__corner:{c}"),
        "hold_tns_ns": m.get(f"timing__hold__tns__corner:{c}"),
        "setup_r2r_ws_ns": m.get(f"timing__setup_r2r__ws__corner:{c}"),
        "fmax_MHz": round(1000.0 / (T - m[f"timing__setup__ws__corner:{c}"]), 2)
        if m.get(f"timing__setup__ws__corner:{c}") is not None else None,
    } for c in corners}
    rec["fmax_slowest_corner_MHz"] = rec["timing"][SLOWEST]["fmax_MHz"]

    post = step_dir(run, "openroad-stapostpnr")
    if post and (post / SLOWEST / "max.rpt").exists():
        shutil.copy(post / SLOWEST / "max.rpt", keep / f"max_{SLOWEST}.rpt")
        cp = critical_path(post / SLOWEST / "max.rpt")
        cp["source"] = rel(keep / f"max_{SLOWEST}.rpt")
        rec["critical_path_slowest"] = cp

    pre = step_dir(run, "openroad-staprepnr")
    if pre and post:
        pre_m = json.loads((pre / "state_out.json").read_text()).get("metrics", {})
        ws_pre = pre_m.get(f"timing__setup__ws__corner:{PRE_POST_CORNER}")
        ws_post = m.get(f"timing__setup__ws__corner:{PRE_POST_CORNER}")
        if ws_pre is not None and ws_post is not None:
            d_pre, d_post = T - ws_pre, T - ws_post
            rec["post_synth_vs_post_route"] = {
                "corner": PRE_POST_CORNER,
                "post_synth_delay_ns": round(d_pre, 4), "post_route_delay_ns": round(d_post, 4),
                "degradation_ns": round(d_post - d_pre, 4),
                "degradation_percent": round(100 * (d_post - d_pre) / d_pre, 1),
                "note": "delay = T - setup WS (worst path, any type) at the same corner and clock",
                "sources": [rel(pre / "state_out.json"), rec["metrics_source"]]}
        if (pre / PRE_POST_CORNER / "max.rpt").exists():
            shutil.copy(pre / PRE_POST_CORNER / "max.rpt", keep / f"prepnr_max_{PRE_POST_CORNER}.rpt")

    rec["physical"] = {"route_wirelength_um": m.get("route__wirelength"),
                       "max_fanout_violations": m.get("design__max_fanout_violation__count"),
                       f"max_slew_violations_{SLOWEST}": m.get(f"design__max_slew_violation__count__corner:{SLOWEST}")}
    rec["signoff_flow_counts"] = {
        "magic_drc_errors": m.get("magic__drc_error__count"),
        "klayout_drc_errors": m.get("klayout__drc_error__count"),
        "lvs_errors": m.get("design__lvs_error__count"),
        "antenna_violating_nets": m.get("antenna__violating__nets"),
        "route_drc_errors": m.get("route__drc_errors")}
    rec["power_default_activity_W"] = {"value": m.get("power__total"),
                                       "label": "LibreLane default activity (not annotated)"}

    pw = REPO / "sim_build" / "gls" / run.name / "power.json"
    if pw.exists():
        p = json.loads(pw.read_text())
        shutil.copy(pw, keep / "power.json")
        if (pw.parent / "power.rpt").exists():
            shutil.copy(pw.parent / "power.rpt", keep / "power.rpt")
        rec["power_annotated"] = {
            "gate_level_sim": p["gate_level_sim"]["status"],
            "results_checked": p["gate_level_sim"]["results_checked"],
            "total_W": p.get("power", {}).get("total_W"),
            "internal_W": p.get("power", {}).get("internal_W"),
            "switching_W": p.get("power", {}).get("switching_W"),
            "leakage_W": p.get("power", {}).get("leakage_W"),
            "annotation": p.get("power", {}).get("annotation"),
            "energy_per_op_pJ": p.get("energy_per_op_pJ"),
            "period_ns": p["period_ns"], "mix": p["mix"], "note": p["note"],
            "source": rel(keep / "power.json")}
    return rec


def main() -> int:
    summary = {"brief": "docs/BRIEF.md A4/A5", "pdk": "sky130A / sky130_fd_sc_hd",
               "closing_criterion": f"setup WS >= 0 at {SLOWEST} and hold WS >= 0 at all corners",
               "period_resolution_ns": 0.25, "variants": {}}
    for variant in VARIANT_DIRS:
        summary["variants"][variant] = {a: r for a in ADDERS if (r := one(variant, a)) is not None}
    abc = RES / "abc_experiment.json"
    if abc.exists():
        summary["abc_experiment"] = {"source": rel(abc), "results": [
            {k: r.get(k) for k in ("arch", "variant", "cells", "area_um2", "r2r_path_delay_ns")}
            | {"logic_depth": r["critical_path"]["logic_depth"]}
            for r in json.loads(abc.read_text())["results"]]}
    out = REPO / "results" / "summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    for v, archs in summary["variants"].items():
        for a, r in archs.items():
            print(f"{v:<9} {a:<5} {r['sweep_status']:<10} T={r.get('min_period_ns')} "
                  f"fmax_ss={r.get('fmax_slowest_corner_MHz')} MHz "
                  f"area={r.get('area', {}).get('stdcell_area_um2')} "
                  f"E/op={r.get('power_annotated', {}).get('energy_per_op_pJ')}")
    print(f"-> {rel(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
