#!/usr/bin/env python3
"""Aggregate every verification result into results/verify_summary.json (BRIEF Phase 3).

Reads only machine-generated result files; it never computes or types a number
itself. Every entry carries the path of the file it came from.

Gate (PROGRESS.md Phase 3): all 8 adder configurations pass directed + >= 1e6
random vectors on Verilator, coverage is 100% of defined bins, every formal
task passes, lint is clean and the golden-model checks pass.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402

RES = REPO / "results"
MIN_VECTORS = 1_000_000


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def main() -> int:
    checks = {}
    problems = []

    lint = load(RES / "lint_summary.json")
    checks["lint"] = {"result": lint["result"] if lint else "MISSING", "configs": lint and lint["configs"],
                      "source": rel(RES / "lint_summary.json")}

    model_txt = RES / "model_test.txt"
    m = re.search(r"(\d+) passed", model_txt.read_text()) if model_txt.exists() else None
    xc = load(RES / "model_xcheck.json")
    checks["model"] = {"pytest_passed": int(m.group(1)) if m else None,
                       "pytest_failed": "failed" in model_txt.read_text() if model_txt.exists() else None,
                       "spike_xcheck": xc and xc["result"], "spike_vectors": xc and xc["vectors"],
                       "sources": [rel(model_txt), rel(RES / "model_xcheck.json")]}

    sims = []
    for f in sorted((RES / "sim").glob("*.json")):
        r = load(f)
        sims.append({"config": r["config"], "status": r["status"], "random_vectors": r["random_vectors"],
                     "results_checked": r["results_checked"], "coverage_percent": r["coverage_percent"],
                     "seed": r["seed"], "source": rel(f)})
    checks["simulation"] = sims

    # Gate: each architecture on Verilator, PIPE=0, >= 1e6 random vectors, PASS, coverage 100%.
    gate_cfgs = {}
    for arch in ADDERS:
        r = next((s for s in sims if s["config"] == f"verilator_{arch}_PIPE0"), None)
        ok = (r is not None and r["status"] == "PASS" and r["random_vectors"] >= MIN_VECTORS
              and r["coverage_percent"] == 100.0)
        gate_cfgs[arch] = "PASS" if ok else ("MISSING" if r is None else "FAIL")
        if not ok:
            problems.append(f"sim gate {arch}: {r and (r['status'], r['random_vectors'], r['coverage_percent'])}")
    other_fail = [s["config"] for s in sims if s["status"] != "PASS"]
    problems += [f"sim {c} FAIL" for c in other_fail]

    formal = load(RES / "formal" / "summary.json")
    checks["formal"] = {"result": formal["result"] if formal else "MISSING",
                        "subset": formal and formal["subset"], "tasks": formal and formal["tasks"],
                        "passed": formal and formal["passed"], "failed": formal and formal["failed"],
                        "source": rel(RES / "formal" / "summary.json")}

    if not lint or lint["result"] != "PASS":
        problems.append("lint not PASS")
    if not (m and xc and xc["result"] == "PASS") or checks["model"]["pytest_failed"]:
        problems.append("model checks not PASS")
    if not formal or formal["result"] != "PASS" or formal["subset"] != "full":
        problems.append("formal not PASS on the full task set")

    summary = {
        "result": "PASS" if not problems else "FAIL",
        "gate": {"adder_configs_sim": gate_cfgs, "min_random_vectors": MIN_VECTORS,
                 "coverage_required_percent": 100.0},
        "problems": problems,
        "checks": checks,
    }
    out = RES / "verify_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"verify_summary: {summary['result']} -> {rel(out)}")
    for p in problems:
        print("  problem:", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
