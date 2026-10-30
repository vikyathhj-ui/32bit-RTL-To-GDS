#!/usr/bin/env python3
"""Run every SymbiYosys proof and collect the results (BRIEF A3 formal 1-3).

Jobs (in formal/):
  adder_eq.sby   one task per adder architecture (8): adder == a + b + cin
  alu_equiv.sby  one task per ADDER x PIPE (16): alu_top == behavioural reference
  protocol.sby   one task per PIPE (2): out_valid latency L = 2 + PIPE

Each task's verdict is read from its SBY `status` file (PASS/FAIL/ERROR/UNKNOWN)
and its log; results go to results/formal/summary.json. Task directories stay in
formal/<job>_<task>/ (git-ignored), including counterexample traces on failure.

Run inside the iic-osic container from the repo root:
    python3 scripts/run_formal.py                 # everything
    python3 scripts/run_formal.py --job adder_eq  # one job
    python3 scripts/run_formal.py --quick         # CI subset (see --help)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORMAL = REPO / "formal"
OUT = REPO / "results" / "formal" / "summary.json"

JOBS = {
    "adder_eq": "per-architecture adder miter: adder(a,b,cin) == a+b+cin",
    "alu_equiv": "full ALU vs behavioural reference (formal/alu_ref_beh.sv)",
    "protocol": "out_valid follows in_valid with latency L = 2 + PIPE",
}
# CI subset: every adder miter and both protocol proofs, plus ALU equivalence for
# BEH and one prefix adder at both PIPE values (DECISIONS D-020).
QUICK = {"alu_equiv": ["BEH_P0", "BEH_P1", "KS_P0", "KS_P1"]}


def tasks_of(job: str) -> list[str]:
    text = (FORMAL / f"{job}.sby").read_text()
    block = text.split("[tasks]", 1)[1].split("[", 1)[0]
    return [line.strip() for line in block.splitlines() if line.strip() and not line.startswith("#")]


def run_job(job: str, tasks: list[str], jobs: int) -> list[dict]:
    t0 = time.time()
    cmd = ["sby", "-f", "-j", str(jobs), f"{job}.sby", *tasks]
    p = subprocess.run(cmd, cwd=FORMAL, capture_output=True, text=True)
    log = REPO / "sim_build" / "formal" / f"{job}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(" ".join(cmd) + "\n\n" + p.stdout + p.stderr)
    results = []
    for task in tasks:
        d = FORMAL / f"{job}_{task}"
        status = (d / "status").read_text().split()[0] if (d / "status").exists() else "ERROR"
        task_log = (d / "logfile.txt").read_text(errors="replace") if (d / "logfile.txt").exists() else ""
        secs = re.search(r"Elapsed clock time \[H:MM:SS \(secs\)\]: [\d:]+ \((\d+)\)", task_log)
        method = re.search(r"summary: (successful proof by k-induction|.*counterexample.*)", task_log)
        traces = sorted(str(t.relative_to(REPO)) for t in d.glob("engine_*/trace*.vcd")) if status != "PASS" else []
        results.append({
            "job": job, "task": task, "property": JOBS[job], "status": status,
            "seconds": int(secs.group(1)) if secs else None,
            "method": method.group(1) if method else None,
            "engine": "smtbmc yices",
            "log": str((d / "logfile.txt").relative_to(REPO)),
            "counterexample": traces,
        })
    print(f"{job}: {sum(r['status'] == 'PASS' for r in results)}/{len(results)} PASS "
          f"({time.time() - t0:.0f}s wall)")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--job", choices=list(JOBS), action="append")
    ap.add_argument("--quick", action="store_true", help="CI subset: " + json.dumps(QUICK))
    ap.add_argument("-j", "--jobs", type=int, default=3, help="parallel SBY tasks (RAM-bound)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    results = []
    for job in args.job or list(JOBS):
        tasks = tasks_of(job)
        if args.quick and job in QUICK:
            tasks = [t for t in tasks if t in QUICK[job]]
        results += run_job(job, tasks, args.jobs)

    failed = [f"{r['job']}_{r['task']}" for r in results if r["status"] != "PASS"]
    tool = subprocess.run(["sby", "--version"], capture_output=True, text=True).stdout.strip()
    summary = {"check": "SymbiYosys proofs (mode prove)", "tool": tool,
               "subset": "quick (CI)" if args.quick else "full",
               "result": "PASS" if not failed else "FAIL", "tasks": len(results),
               "passed": len(results) - len(failed), "failed": failed, "results": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"formal: {summary['result']}  {summary['passed']}/{len(results)} tasks -> "
          f"{args.out.relative_to(REPO) if args.out.is_relative_to(REPO) else args.out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
