#!/usr/bin/env python3
"""Run LibreLane once for one adder architecture at one clock period (BRIEF A4).

Renders flow/config.template.json into runs/<ARCH>_P<pipe>_T<period>/config.json,
runs the Classic flow with --design-dir set to the repo root (so the run lands in
runs/<tag>/), and returns a small record parsed from final/metrics.json.

"Closes" (DECISIONS D-023): setup WS >= 0 at the slowest corner max_ss_100C_1v60
and hold WS >= 0 at every corner, with the flow finished. Runs that already
finished are reused, not rerun.

Run inside the iic-osic container from the repo root:
    python3 scripts/flow_run.py --adder BEH --period 10
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402
from lint import TOP_FILES  # noqa: E402

TEMPLATE = REPO / "flow" / "config.template.json"
RUNS = REPO / "runs"
SLOWEST = "max_ss_100C_1v60"
# Setup-repair margin as a fraction of the clock period (DECISIONS D-029): the
# resizer works from placement / global-routing parasitic estimates, which came
# out ~9.5% optimistic at max_ss versus the final extracted wires, so repair
# aims for slack >= SETUP_MARGIN_FRAC * T. Same rule for every architecture.
SETUP_MARGIN_FRAC = 0.12
# Flow variants (DECISIONS D-026/D-027). "default" is the stock LibreLane flow.
# "preserved" keeps the hand-written prefix/lookahead cells as separate modules
# through synthesis so ABC cannot restructure the adder tree; all else identical.
VARIANTS = {
    "default": {},
    "preserved": {"SLANG_ARGUMENTS": ["--keep-hierarchy"],
                  "SYNTH_KEEP_HIERARCHY_MODULES": ["pg_black*", "pg_gray*", "cla4_unit*", "adder_rca*"]},
}


def tag(arch: str, period: float, pipe: int = 0, variant: str = "default") -> str:
    suffix = "" if variant == "default" else f"_{variant}"
    return f"{arch}_P{pipe}_T{period:.2f}{suffix}"


def corners(metrics: dict) -> list[str]:
    pre = "timing__setup__ws__corner:"
    return sorted(k[len(pre):] for k in metrics if k.startswith(pre))


def evaluate(metrics: dict) -> dict:
    """Closing decision from final metrics (D-023)."""
    cs = corners(metrics)
    setup_slow = metrics.get(f"timing__setup__ws__corner:{SLOWEST}")
    hold_min = min((metrics[f"timing__hold__ws__corner:{c}"] for c in cs), default=None)
    closes = (setup_slow is not None and hold_min is not None
              and setup_slow >= 0 and hold_min >= 0)
    return {"setup_ws_slowest": setup_slow, "hold_ws_min": hold_min,
            "closes": closes, "corners": len(cs)}


def run(arch: str, period: float, pipe: int = 0, quiet: bool = True, variant: str = "default") -> dict:
    t = tag(arch, period, pipe, variant)
    rundir = RUNS / t
    # LibreLane writes <design-dir>/runs/<tag>/final/; a finished run is reused, never re-run
    # (re-running with the same tag appends a second set of steps to the same directory).
    metrics_file = rundir / "runs" / t / "final" / "metrics.json"
    rec = {"arch": arch, "pipe": pipe, "variant": variant, "period_ns": round(period, 2), "tag": t,
           "run_dir": str(rundir.relative_to(REPO))}

    if not metrics_file.exists():
        rundir.mkdir(parents=True, exist_ok=True)
        cfg = TEMPLATE.read_text()
        cfg = (cfg.replace('"@VERILOG_FILES@"', json.dumps([f"dir::../../{f}" for f in TOP_FILES]))
                  .replace("@ADDER_CODE@", str(ADDERS[arch]))
                  .replace("@PIPE@", str(pipe))
                  .replace('"@CLOCK_PERIOD@"', f"{period:.2f}"))
        margin = round(SETUP_MARGIN_FRAC * period, 3)
        cfg_obj = json.loads(cfg) | VARIANTS[variant] | {
            "PL_RESIZER_SETUP_SLACK_MARGIN": margin, "GRT_RESIZER_SETUP_SLACK_MARGIN": margin}
        cfg_path = rundir / "config.json"
        cfg_path.write_text(json.dumps(cfg_obj, indent=4) + "\n")
        cmd = ["librelane", "--manual-pdk", "--pdk-root", os.environ["PDK_ROOT"],
               "--pdk", "sky130A", "--scl", "sky130_fd_sc_hd",
               "--run-tag", t, "--design-dir", str(rundir), "--condensed", str(cfg_path)]
        t0 = time.time()
        with open(rundir / "librelane.log", "w") as log:
            p = subprocess.run(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
        rec["seconds"] = round(time.time() - t0)
        rec["exit"] = p.returncode
    # LibreLane puts runs under <design-dir>/runs/<tag>; normalise the path.
    inner = rundir / "runs" / t
    if inner.exists():
        metrics_file = inner / "final" / "metrics.json"
        rec["run_dir"] = str(inner.relative_to(REPO))
    if not metrics_file.exists():
        rec.update({"closes": False, "status": "FLOW_FAILED",
                    "log": str((rundir / "librelane.log").relative_to(REPO))})
    else:
        m = json.loads(metrics_file.read_text())
        rec.update(evaluate(m))
        rec["status"] = "CLOSES" if rec["closes"] else "FAILS_TIMING"
        rec["metrics"] = str(metrics_file.relative_to(REPO))
    if not quiet:
        print(json.dumps(rec, indent=2))
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--adder", required=True, choices=list(ADDERS))
    ap.add_argument("--period", type=float, required=True, help="clock period in ns")
    ap.add_argument("--pipe", type=int, default=0, choices=[0, 1])
    ap.add_argument("--variant", default="default", choices=list(VARIANTS))
    a = ap.parse_args(argv)
    rec = run(a.adder, a.period, a.pipe, quiet=False, variant=a.variant)
    return 0 if rec["status"] != "FLOW_FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
