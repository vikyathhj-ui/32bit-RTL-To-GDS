#!/usr/bin/env python3
"""Run the gate-level power flow (scripts/gls_power.py) on every finished sweep's closing run.

For each flow variant and architecture whose sweep is DONE, the run at the
minimum closing period is simulated with the workload mix at that period and
its activity-annotated power is measured (DECISIONS D-025). Results land in
sim_build/gls/<run>/power.json and are collected by scripts/parse_flow.py.

Run inside the iic-osic container from the repo root:
    .venv/bin/python scripts/power_all.py [--ops 10000]
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import gls_power  # noqa: E402

SWEEPS = {"default": REPO / "results" / "flow" / "sweep",
          "preserved": REPO / "results" / "flow" / "sweep_preserved"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ops", type=int, default=10000)
    ap.add_argument("--force", action="store_true", help="rerun even if power.json exists")
    a = ap.parse_args(argv)
    failures = []
    for variant, d in SWEEPS.items():
        for f in sorted(d.glob("*.json")):
            s = json.loads(f.read_text())
            if s.get("status") != "DONE":
                print(f"skip {variant} {s['arch']}: sweep {s.get('status') or 'RUNNING'}")
                continue
            run = next(r["run_dir"] for r in s["runs"] if r["period_ns"] == s["min_period_ns"])
            done = REPO / "sim_build" / "gls" / Path(run).name / "power.json"
            if done.exists() and not a.force:
                print(f"have {variant} {s['arch']}: {done.relative_to(REPO)}")
                continue
            print(f"power {variant} {s['arch']} at T={s['min_period_ns']} ns ({run})", flush=True)
            rec = gls_power.main(["--run", run, "--ops", str(a.ops)])
            if rec["gate_level_sim"]["status"] != "PASS" or not rec.get("energy_per_op_pJ"):
                failures.append(f"{variant} {s['arch']}")
    for x in failures:
        print("FAILED:", x)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
