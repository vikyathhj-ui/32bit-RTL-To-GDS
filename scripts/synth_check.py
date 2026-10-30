#!/usr/bin/env python3
"""Check that Yosys (slang frontend) synthesises every alu_top configuration.

For each ADDER (8) x PIPE (0, 1): read_slang -> synth -flatten -> checks.
A configuration fails on any Yosys error, any latch, or any problem reported by
`check -assert` (multiple drivers, undriven wires, combinational loops).

This is a pass/fail gate only. No area or timing numbers are reported: generic
Yosys gates mean nothing for SKY130 PPA, which comes from LibreLane in Phase 4.

Run inside the iic-osic container from the repo root:
    python3 scripts/synth_check.py   # writes results/synth_check.json, logs in sim_build/synth/
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402
from lint import TOP_FILES  # noqa: E402  (same file list and order as lint)

LOGDIR = REPO / "sim_build" / "synth"
OUT = REPO / "results" / "synth_check.json"

LATCH_TYPES = ("$dlatch", "$adlatch", "$dlatchsr", "$_DLATCH_", "$_DLATCHSR_", "$_SR_")


def synth(arch: str, code: int, pipe: int) -> dict:
    name = f"alu_top_{arch}_PIPE{pipe}"
    script = "; ".join([
        f"read_slang --top alu_top -GADDER={code} -GPIPE={pipe} {' '.join(TOP_FILES)}",
        "synth -flatten -top alu_top",
        "check -assert",
        "stat",
    ])
    p = subprocess.run(["yosys", "-p", script], cwd=REPO, capture_output=True, text=True)
    log = LOGDIR / f"{name}.log"
    out = p.stdout + p.stderr
    log.write_text(out)
    # `stat` lists one "<count> <cell type>" line per type; add up every latch type.
    latches = sum(int(n) for t in LATCH_TYPES
                  for n in re.findall(rf"^\s+(\d+)\s+{re.escape(t)}\S*\s*$", out, re.M))
    errors = re.findall(r"^ERROR:.*$", out, re.M)
    ok = p.returncode == 0 and latches == 0 and not errors
    return {"config": name, "params": {"ADDER": code, "PIPE": pipe},
            "status": "PASS" if ok else "FAIL", "latches": latches,
            "errors": errors[:5], "exit": p.returncode, "log": str(log.relative_to(REPO)),
            "command": f"yosys -p '{script}'"}


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    jobs = [(a, c, p) for a, c in ADDERS.items() for p in (0, 1)]
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda j: synth(*j), jobs))

    for r in results:
        extra = f" {r['errors'][0]}" if r["errors"] else ""
        print(f"{r['status']}  {r['config']:<20} latches={r['latches']}{extra}")
    failed = [r["config"] for r in results if r["status"] != "PASS"]
    summary = {
        "check": "yosys read_slang + synth -flatten + check -assert, no latches",
        "tool": subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip(),
        "result": "PASS" if not failed else "FAIL",
        "configs": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "results": results,
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"synth_check: {summary['result']}  {summary['passed']}/{len(results)} configs -> "
          f"{OUT.relative_to(REPO)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
