#!/usr/bin/env python3
"""Phase 2 gate: `verilator --lint-only -Wall` on every RTL configuration.

Checks:
  - alu_top for every ADDER (8) x PIPE (0, 1) = 16 configurations;
  - each adder module on its own (adder_<arch>, W = 32), so a warning inside an
    architecture is not hidden by the wrapper.
A configuration passes only with zero warnings and exit status 0. Inline
waivers (`verilator lint_off`) are listed so they stay visible.

Run inside the iic-osic container from the repo root:
    python3 scripts/lint.py        # writes results/lint_summary.json, logs in sim_build/lint/
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402

RTL = REPO / "rtl"
LOGDIR = REPO / "sim_build" / "lint"
OUT = REPO / "results" / "lint_summary.json"

# Compile order: package first, then everything else.
TOP_FILES = (["rtl/alu_pkg.sv"]
             + sorted(str(p.relative_to(REPO)) for p in (RTL / "adders").glob("*.sv"))
             + ["rtl/shifter.sv", "rtl/clz_tree.sv", "rtl/clz.sv", "rtl/cpop.sv", "rtl/alu_top.sv"])
# Architecture modules do not import alu_pkg; only the selector (adder.sv) does.
ADDER_FILES = sorted(str(p.relative_to(REPO)) for p in (RTL / "adders").glob("*.sv")
                     if p.name != "adder.sv")
ARCH_MODULE = {"RCA": "adder_rca", "CLA4": "adder_cla4", "CSLA": "adder_csla", "BK": "adder_bk",
               "KS": "adder_ks", "SK": "adder_sk", "HC": "adder_hc", "BEH": "adder_beh"}

WARN = re.compile(r"^%(Warning|Error)(-[A-Z0-9_]+)?:", re.M)


def lint(name: str, top: str, files: list[str], params: dict[str, int]) -> dict:
    cmd = ["verilator", "--lint-only", "-Wall", "--top-module", top]
    cmd += [f"-G{k}={v}" for k, v in params.items()] + files
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    log = LOGDIR / f"{name}.log"
    log.write_text(" ".join(cmd) + "\n\n" + p.stdout + p.stderr)
    msgs = [m.group(0) for m in WARN.finditer(p.stdout + p.stderr)
            if "Exiting due to" not in (p.stdout + p.stderr)[m.start():m.start() + 80]]
    warnings = len([m for m in msgs if m.startswith("%Warning")])
    errors = len([m for m in msgs if m.startswith("%Error")])
    ok = p.returncode == 0 and warnings == 0 and errors == 0
    return {"config": name, "top": top, "params": params, "status": "PASS" if ok else "FAIL",
            "warnings": warnings, "errors": errors, "exit": p.returncode,
            "log": str(log.relative_to(REPO)), "command": " ".join(cmd)}


def find_waivers() -> list[str]:
    found = []
    for f in sorted(RTL.rglob("*.sv")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if "lint_off" in line:
                found.append(f"{f.relative_to(REPO)}:{n}: {line.strip()}")
    return found


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    results = []
    for arch, code in ADDERS.items():
        for pipe in (0, 1):
            results.append(lint(f"alu_top_{arch}_PIPE{pipe}", "alu_top", TOP_FILES,
                                {"ADDER": code, "PIPE": pipe}))
    for arch, module in ARCH_MODULE.items():
        results.append(lint(f"{module}_W32", module, ADDER_FILES, {"W": 32}))

    for r in results:
        print(f"{r['status']}  {r['config']:<22} warnings={r['warnings']} errors={r['errors']}")
        if r["status"] != "PASS":
            # Show the messages themselves (CI keeps only stdout, not sim_build/ logs).
            text = (REPO / r["log"]).read_text()
            for line in [ln for ln in text.splitlines() if ln.startswith(("%Warning", "%Error"))][:8]:
                print("      " + line)
    waivers = find_waivers()
    failed = [r["config"] for r in results if r["status"] != "PASS"]
    summary = {
        "check": "verilator --lint-only -Wall",
        "tool": subprocess.run(["verilator", "--version"], capture_output=True, text=True).stdout.strip(),
        "result": "PASS" if not failed else "FAIL",
        "configs": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "waivers": waivers,
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"lint: {summary['result']}  {summary['passed']}/{len(results)} configs clean, "
          f"{len(waivers)} inline waivers -> {OUT.relative_to(REPO)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
