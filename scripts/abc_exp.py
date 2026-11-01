#!/usr/bin/env python3
"""ABC structure experiment (BRIEF A4 "Structure check", DECISIONS D-026).

Question: does LibreLane's default synthesis (Yosys + ABC with the default
area-oriented strategy) keep the hand-written adder structures, or does ABC
restructure them so the architectural differences disappear?

For each architecture, the adder alone (flow/adder_wrap.sv: registers ->
adder -> registers) is synthesised twice with the same flow settings as the
sweep, stopping after pre-PnR STA:
  default    LibreLane default: hierarchy flattened, default ABC script
  preserved  slang --keep-hierarchy + keep_hierarchy on the prefix/lookahead
             cells (pg_black, pg_gray, cla4_unit, adder_rca), so ABC maps each
             cell on its own and cannot rebuild the tree
Measured: the worst register-to-register path of each synthesised netlist
(OpenSTA, tt_025C_1v80 liberty, ideal clock, no wire parasitics): its logic
depth (combinational cells on the path) and data-arrival delay; plus cell count,
cell area and the cell-type mix from Yosys.

Run inside the iic-osic container from the repo root:
    python3 scripts/abc_exp.py            # -> results/flow/abc_experiment.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402

RUNS = REPO / "runs" / "abc"
OUT = REPO / "results" / "flow" / "abc_experiment.json"
PERIOD = 10.0
CORNER = "nom_tt_025C_1v80"
ADDER_FILES = (["rtl/alu_pkg.sv"]
               + sorted(str(p.relative_to(REPO)) for p in (REPO / "rtl" / "adders").glob("*.sv"))
               + ["flow/adder_wrap.sv"])
KEEP = ["pg_black*", "pg_gray*", "cla4_unit*", "adder_rca*"]
# Output pins of combinational cells on a path (flop Q pins are the launch point, not depth).
# OpenSTA prints "... <arrival> ^ <inst>/<pin> (<cell type>)".
OUT_PIN = re.compile(r"\s(\S+)/(X|Y|SUM|COUT)\s+\((sky130_fd_sc_hd__\w+)\)")


def config(arch: str, variant: str) -> dict:
    cfg = {
        "DESIGN_NAME": "adder_wrap",
        "VERILOG_FILES": [f"dir::../../../{f}" for f in ADDER_FILES],
        "USE_SLANG": True,
        "SYNTH_PARAMETERS": [f"ARCH={ADDERS[arch]}"],
        "CLOCK_PORT": "clk",
        "CLOCK_PERIOD": PERIOD,
        "FP_SIZING": "relative",
        "FP_CORE_UTIL": 40,
        "PL_TARGET_DENSITY_PCT": 50,
    }
    if variant == "preserved":
        cfg["SLANG_ARGUMENTS"] = ["--keep-hierarchy"]
        cfg["SYNTH_KEEP_HIERARCHY_MODULES"] = KEEP
    return cfg


def critical_path(rpt: Path) -> dict:
    text = rpt.read_text()
    first = text.split("Startpoint:", 2)
    path = "Startpoint:" + first[1] if len(first) > 1 else ""
    cells = [(m.group(3).replace("sky130_fd_sc_hd__", ""), m.group(1)) for m in OUT_PIN.finditer(path)]
    sp = re.search(r"Startpoint: (\S+)", path)
    ep = re.search(r"Endpoint: (\S+)", path)
    arr = re.search(r"([\d.]+)\s+data arrival time", path)
    return {"startpoint": sp and sp.group(1), "endpoint": ep and ep.group(1),
            "data_arrival_ns": float(arr.group(1)) if arr else None,
            "logic_depth": len(cells), "cells": [c for c, _ in cells]}


LIB = Path(os.environ.get("PDK_ROOT", "/foss/pdks")) / "sky130A" / "libs.ref" / "sky130_fd_sc_hd" / "lib" / \
    "sky130_fd_sc_hd__tt_025C_1v80.lib"


def r2r_path(netlist: Path, work: Path) -> dict:
    """Worst register-to-register path of a synthesised netlist (OpenSTA, tt corner, ideal clock).

    The flow's own pre-PnR max.rpt shows the worst path of any kind, which for a
    fast adder is an output-port path set by the 20% I/O delay; the experiment
    needs the adder's own register-to-register path.
    """
    tcl = work / "r2r.tcl"
    rpt = work / "r2r.rpt"
    tcl.write_text("\n".join([
        f"read_liberty {LIB}",
        f"read_verilog {netlist}",
        "link_design adder_wrap",
        f"create_clock -name clk -period {PERIOD} [get_ports clk]",
        "report_checks -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins] "
        "-fields {fanout cap slew} -digits 4",
        "exit",
    ]) + "\n")
    p = subprocess.run(["sta", "-no_splash", "-exit", str(tcl)], capture_output=True, text=True)
    rpt.write_text(p.stdout + p.stderr)
    cp = critical_path(rpt)
    cp["report"] = str(rpt.relative_to(REPO))
    return cp


def run_one(arch: str, variant: str) -> dict:
    rundir = RUNS / f"{arch}_{variant}"
    tagname = f"{arch}_{variant}"
    inner = rundir / "runs" / tagname
    if not (inner / "runtime.txt").exists() and not list(inner.glob("*-openroad-staprepnr")):
        rundir.mkdir(parents=True, exist_ok=True)
        (rundir / "config.json").write_text(json.dumps(config(arch, variant), indent=2) + "\n")
        cmd = ["librelane", "--manual-pdk", "--pdk-root", os.environ["PDK_ROOT"], "--pdk", "sky130A",
               "--scl", "sky130_fd_sc_hd", "--run-tag", tagname, "--design-dir", str(rundir),
               "--to", "OpenROAD.STAPrePNR", "--condensed", str(rundir / "config.json")]
        with open(rundir / "librelane.log", "w") as log:
            subprocess.run(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
    rec = {"arch": arch, "variant": variant, "run_dir": str(inner.relative_to(REPO))}
    synth = next(iter(inner.glob("*-yosys-synthesis")), None)
    sta = next(iter(inner.glob("*-openroad-staprepnr")), None)
    if not synth or not sta or not (sta / CORNER / "max.rpt").exists():
        rec["status"] = "FAILED"
        return rec
    stat = json.loads((synth / "reports" / "stat.json").read_text())["design"]
    by_type = {k.replace("sky130_fd_sc_hd__", ""): v for k, v in stat.get("num_cells_by_type", {}).items()}
    metrics = json.loads((sta / "state_out.json").read_text()).get("metrics", {})
    ws = metrics.get(f"timing__setup__ws__corner:{CORNER}")
    r2r = r2r_path(synth / "adder_wrap.nl.v", rundir)
    rec.update({
        "status": "OK",
        "cells": stat.get("num_cells"), "area_um2": stat.get("area"),
        "top_cell_types": dict(sorted(by_type.items(), key=lambda kv: -kv[1])[:10]),
        "r2r_path_delay_ns": r2r["data_arrival_ns"],
        "critical_path": r2r,
        "flow_setup_ws_any_path_ns": ws,
        "sources": {"stat": str((synth / "reports" / "stat.json").relative_to(REPO)),
                    "r2r_rpt": r2r["report"],
                    "flow_max_rpt": str((sta / CORNER / "max.rpt").relative_to(REPO))},
    })
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--adder", action="append", choices=list(ADDERS))
    a = ap.parse_args(argv)
    jobs = [(arch, v) for arch in (a.adder or list(ADDERS)) for v in ("default", "preserved")]
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        recs = list(ex.map(lambda j: run_one(*j), jobs))
    for r in recs:
        cp = r.get("critical_path", {})
        print(f"{r['arch']:<5} {r['variant']:<9} {r['status']:<6} depth={cp.get('logic_depth')} "
              f"r2r_delay={r.get('r2r_path_delay_ns')} ns cells={r.get('cells')} area={r.get('area_um2')}")
    out = {"experiment": "adder alone (flow/adder_wrap.sv), synthesis + pre-PnR STA",
           "corner": CORNER, "period_ns": PERIOD, "keep_hierarchy_modules": KEEP,
           "results": recs}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    return 0 if all(r["status"] == "OK" for r in recs) else 1


if __name__ == "__main__":
    sys.exit(main())
