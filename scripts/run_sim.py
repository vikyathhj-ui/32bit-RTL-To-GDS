#!/usr/bin/env python3
"""Build and run the cocotb testbench (tb/alu_tb.py) for one or more configurations.

Each run: simulator x ADDER x PIPE, with N random vectors and a seed. Results
per run go to results/sim/<sim>_<ADDER>_PIPE<p>.json (pass/fail per test,
vectors, seed, coverage, tool version, command) plus coverage JSON/YAML in
results/coverage/. Build and log files stay in sim_build/ (not committed).

Examples (inside the iic-osic container, repo root):
    .venv/bin/python scripts/run_sim.py --sim verilator --adder KS --vectors 10000
    .venv/bin/python scripts/run_sim.py --sim verilator --adder all --vectors 1000000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
# The cocotb runner builds the simulator's PYTHONPATH from this process
# (extra_env PYTHONPATH is overridden), so the testbench and model go here.
for _p in (REPO / "tb", REPO / "model"):
    sys.path.insert(0, str(_p))
os.environ["PYTHONPATH"] = os.pathsep.join([str(REPO / "tb"), str(REPO / "model"),
                                            os.environ.get("PYTHONPATH", "")])

from adders import ADDERS  # noqa: E402
from lint import TOP_FILES  # noqa: E402

from cocotb_tools.runner import get_runner  # noqa: E402


def tool_version(sim: str) -> str:
    cmd = ["verilator", "--version"] if sim == "verilator" else ["iverilog", "-V"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return (out.stdout + out.stderr).strip().splitlines()[0]


def run_one(sim: str, arch: str, pipe: int, vectors: int, seed: int, tests: list[str] | None) -> dict:
    name = f"{sim}_{arch}_PIPE{pipe}"
    build_dir = REPO / "sim_build" / "cocotb" / name
    cov_out = REPO / "results" / "coverage" / f"{name}.json"
    results_xml = build_dir / "results.xml"
    log_file = build_dir / "sim.log"
    build_dir.mkdir(parents=True, exist_ok=True)

    runner = get_runner(sim)
    build_args = ["-Wno-fatal"] if sim == "verilator" else []  # RTL is lint-clean; don't fail on TB-side notes
    t0 = time.time()
    runner.build(sources=[REPO / f for f in TOP_FILES], hdl_toplevel="alu_top",
                 parameters={"ADDER": ADDERS[arch], "PIPE": pipe}, build_dir=build_dir,
                 build_args=build_args, always=True, log_file=build_dir / "build.log",
                 timescale=("1ns", "1ps"))  # RTL has no `timescale; Icarus would default to 1 s
    env = {"ALU_PIPE": str(pipe), "ALU_VECTORS": str(vectors), "ALU_COV_OUT": str(cov_out),
           "ALU_SEED": str(seed)}
    runner.test(test_module="alu_tb", hdl_toplevel="alu_top", build_dir=build_dir, test_dir=build_dir,
                seed=seed, extra_env=env, results_xml=results_xml, log_file=log_file,
                testcase=tests, parameters={"ADDER": ADDERS[arch], "PIPE": pipe},
                timescale=("1ns", "1ps"))
    elapsed = time.time() - t0

    test_results = {}
    for tc in ET.parse(results_xml).getroot().iter("testcase"):
        failed = tc.find("failure") is not None or tc.find("error") is not None
        test_results[tc.get("name")] = "FAIL" if failed else "PASS"
    log_text = log_file.read_text(errors="replace")
    checked = {m.group(2): int(m.group(3)) for m in
               re.finditer(r"(PASS|FAIL) (test_\w+): (\d+) results checked", log_text)}
    cov = json.loads(cov_out.read_text()) if cov_out.exists() else None
    ok = bool(test_results) and all(v == "PASS" for v in test_results.values())
    rec = {
        "config": name, "simulator": sim, "tool": tool_version(sim), "adder": arch,
        "params": {"ADDER": ADDERS[arch], "PIPE": pipe}, "status": "PASS" if ok else "FAIL",
        "tests": test_results, "results_checked": checked, "random_vectors": vectors,
        "seed": seed, "seconds": round(elapsed, 1),
        "coverage_percent": cov["percent"] if cov else None,
        "coverage_file": str(cov_out.relative_to(REPO)) if cov else None,
        "log": str(log_file.relative_to(REPO)),
        "command": " ".join(["scripts/run_sim.py", "--sim", sim, "--adder", arch, "--pipe", str(pipe),
                             "--vectors", str(vectors), "--seed", str(seed)]),
    }
    out = REPO / "results" / "sim" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"{rec['status']}  {name:<24} checked={checked} cov={rec['coverage_percent']}% "
          f"time={rec['seconds']}s")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sim", choices=["verilator", "icarus"], default="verilator")
    ap.add_argument("--adder", default="BEH", help="architecture name or 'all'")
    ap.add_argument("--pipe", type=int, choices=[0, 1], default=0)
    ap.add_argument("--vectors", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=20261030)
    ap.add_argument("--test", action="append", help="run only this cocotb test (repeatable)")
    args = ap.parse_args(argv)
    archs = list(ADDERS) if args.adder == "all" else [args.adder.upper()]
    recs = [run_one(args.sim, a, args.pipe, args.vectors, args.seed, args.test) for a in archs]
    return 0 if all(r["status"] == "PASS" for r in recs) else 1


if __name__ == "__main__":
    sys.exit(main())
