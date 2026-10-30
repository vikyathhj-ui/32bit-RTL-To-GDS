#!/usr/bin/env python3
"""Gate-level workload simulation + activity-annotated power for one flow run (BRIEF A4, D-025).

1. Simulate the run's post-route netlist (final/nl/alu_top.nl.v) with the PDK's
   functional cell models in Icarus (combinational cells zero-delay; flops and
   latches get `UNIT_DELAY = #1, i.e. 1 ns clock-to-Q, the usual way to avoid
   zero-delay races), driven by tb/workload_tb.py at
   the run's own clock period; every result is checked against the golden model
   and every net is dumped to a VCD (tb/gls_dump.v).
2. OpenSTA: tt_025C_1v80 liberty + the run's netlist, SDC and nominal SPEF, then
   read_vcd and report_power. The fraction of annotated nets is recorded.
3. Energy per operation = total power x clock period (one op per cycle).

Zero-delay simulation has no glitches, so glitch power is not included; this is
stated in every result record.

Run inside the iic-osic container from the repo root:
    .venv/bin/python scripts/gls_power.py --run runs/KS_P0_T20.25/runs/KS_P0_T20.25
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO / "tb", REPO / "model"):
    sys.path.insert(0, str(_p))
os.environ["PYTHONPATH"] = os.pathsep.join([str(REPO / "tb"), str(REPO / "model"),
                                            os.environ.get("PYTHONPATH", "")])

from cocotb_tools.runner import get_runner  # noqa: E402

LIB_DIR = Path(os.environ.get("PDK_ROOT", "/foss/pdks")) / "sky130A" / "libs.ref" / "sky130_fd_sc_hd"
CORNER_LIB = LIB_DIR / "lib" / "sky130_fd_sc_hd__tt_025C_1v80.lib"


def simulate(run: Path, period: float, ops: int, seed: int, work: Path) -> dict:
    # The cocotb Icarus runner makes vvp write FST when waves are enabled (and
    # suppresses dumping entirely otherwise), so dump FST and convert to VCD.
    fst = work / "workload.fst"
    vcd = work / "workload.vcd"
    runner = get_runner("icarus")
    sources = [run / "final" / "nl" / "alu_top.nl.v",
               LIB_DIR / "verilog" / "primitives.v",
               LIB_DIR / "verilog" / "sky130_fd_sc_hd.v",
               REPO / "tb" / "gls_dump.v"]
    runner.build(sources=sources, hdl_toplevel="alu_top", build_dir=work, always=True,
                 defines={"FUNCTIONAL": 1},
                 # Passed raw: the runner would wrap string define values in quotes.
                 build_args=["-s", "gls_dump", "-DUNIT_DELAY=#1", f'-DGLS_VCD="{fst}"'],
                 timescale=("1ns", "1ps"),
                 log_file=work / "build.log")
    results_xml = work / "results.xml"
    runner.test(test_module="workload_tb", hdl_toplevel="alu_top", build_dir=work, test_dir=work,
                extra_env={"ALU_OPS": str(ops), "ALU_SEED": str(seed), "ALU_CLK_NS": f"{period}",
                           "ALU_PIPE": "0"},
                results_xml=results_xml, log_file=work / "sim.log", timescale=("1ns", "1ps"),
                waves=True)  # without this the runner passes vvp -none, which suppresses $dumpvars
    failed = any(tc.find("failure") is not None or tc.find("error") is not None
                 for tc in ET.parse(results_xml).getroot().iter("testcase"))
    if fst.exists():
        with open(vcd, "w") as f:
            subprocess.run(["fst2vcd", str(fst)], stdout=f, check=True)
    log = (work / "sim.log").read_text(errors="replace")
    m = re.search(r"(PASS|FAIL) test_workload: (\d+) results checked, (\d+) errors.*?group counts (\{.*?\})", log)
    return {"status": "FAIL" if failed or not m or m.group(1) != "PASS" else "PASS",
            "results_checked": int(m.group(2)) if m else None,
            "errors": int(m.group(3)) if m else None,
            "group_counts": m.group(4) if m else None,
            "vcd": str(vcd.relative_to(REPO)), "log": str((work / "sim.log").relative_to(REPO))}


def sta_power(run: Path, vcd: Path, work: Path) -> dict:
    spef = run / "final" / "spef" / "nom" / "alu_top.nom.spef"
    tcl = work / "power.tcl"
    tcl.write_text("\n".join([
        f"read_liberty {CORNER_LIB}",
        f"read_verilog {run / 'final' / 'nl' / 'alu_top.nl.v'}",
        "link_design alu_top",
        f"read_sdc {run / 'final' / 'sdc' / 'alu_top.sdc'}",
        f"read_spef {spef}",
        "set_propagated_clock [all_clocks]",
        f"read_vcd -scope alu_top {vcd}",
        "report_activity_annotation",
        "report_power -digits 6",
        "exit",
    ]) + "\n")
    p = subprocess.run(["sta", "-no_splash", "-exit", str(tcl)], capture_output=True, text=True)
    out = p.stdout + p.stderr
    (work / "power.rpt").write_text(out)
    # Total row: "Total  <internal> <switching> <leakage> <total> 100.0%"
    tot = re.search(r"^Total\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", out, re.M)
    ann = {}
    for kind in ("vcd", "unannotated"):
        m = re.search(rf"^\s*{kind}\s+(\d+)", out, re.M | re.I)
        if m:
            ann[kind] = int(m.group(1))
    return {"internal_W": float(tot.group(1)) if tot else None,
            "switching_W": float(tot.group(2)) if tot else None,
            "leakage_W": float(tot.group(3)) if tot else None,
            "total_W": float(tot.group(4)) if tot else None,
            "annotation": ann, "report": str((work / "power.rpt").relative_to(REPO)),
            "corner": "tt_025C_1v80, nominal SPEF", "exit": p.returncode}


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, required=True, help="LibreLane run directory (contains final/)")
    ap.add_argument("--ops", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20261030)
    a = ap.parse_args(argv)
    run = (REPO / a.run).resolve() if not a.run.is_absolute() else a.run
    cfg = json.loads((run / "resolved.json").read_text())
    period = float(cfg["CLOCK_PERIOD"])
    work = REPO / "sim_build" / "gls" / run.name
    work.mkdir(parents=True, exist_ok=True)

    sim = simulate(run, period, a.ops, a.seed, work)
    rec = {"run": str(run.relative_to(REPO)), "period_ns": period, "ops": a.ops, "seed": a.seed,
           "mix": "50% ADD/SUB, 20% AND/OR/XOR, 20% SLL/SRL/SRA, 10% Zbb (uniform), back-to-back",
           "gate_level_sim": sim,
           "note": "functional cell models (zero-delay logic, 1 ns flop clock-to-Q): glitch power not included"}
    if sim["status"] == "PASS":
        pw = sta_power(run, REPO / sim["vcd"], work)
        rec["power"] = pw
        if pw["total_W"] is not None:
            rec["energy_per_op_pJ"] = pw["total_W"] * period * 1e-9 * 1e12
    out = work / "power.json"
    out.write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps(rec, indent=2))
    return rec


if __name__ == "__main__":
    r = main()
    sys.exit(0 if r["gate_level_sim"]["status"] == "PASS" and r.get("energy_per_op_pJ") else 1)
