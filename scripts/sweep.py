#!/usr/bin/env python3
"""Find each adder architecture's minimum closing clock period (BRIEF A4, DECISIONS D-023).

"Closes" = setup WS >= 0 at max_ss_100C_1v60 and hold WS >= 0 at every corner
(scripts/flow_run.py). Search per architecture, 0.25 ns resolution:
  1. seed run at --seed ns;
  2. from a failing run, jump to ceil_0.25(T - WS) (WS < 0), at least +0.25;
     from a closing run with no failing point below, jump to ceil_0.25(T - WS),
     at most -0.25; between a failing lo and a closing hi, bisect;
  3. stop when hi - lo == 0.25 AND hi + 0.25 also closes (monotonicity check).
A closing T whose T + 0.25 fails is a non-monotonic point: it is logged and not
accepted as the minimum. Every run is kept and logged.

Architectures run in parallel (--jobs), each search sequential. Finished runs
are reused, so the sweep can be stopped and restarted.

Run inside the iic-osic container from the repo root:
    python3 scripts/sweep.py                 # all 8, 3 in parallel
    python3 scripts/sweep.py --adder KS --adder BK
Output: results/flow/sweep/<ARCH>.json and results/flow/sweep_log.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import flow_run  # noqa: E402
from adders import ADDERS  # noqa: E402

OUTDIR = REPO / "results" / "flow" / "sweep"
STEP = 0.25
MAX_RUNS = 16


def q_up(t: float) -> float:
    return math.ceil(round(t / STEP, 6)) * STEP


def search(arch: str, seed: float, pipe: int) -> dict:
    hist: dict[float, dict] = {}
    t_start = time.time()

    def probe(t: float) -> dict:
        t = round(round(t / STEP) * STEP, 2)
        if t not in hist:
            r = flow_run.run(arch, t, pipe)
            hist[t] = r
            print(f"[{arch}] T={t:5.2f} {r['status']:<13} setup_ws(max_ss)={r.get('setup_ws_slowest')} "
                  f"hold_ws_min={r.get('hold_ws_min')}", flush=True)
            save()
        return hist[t]

    def save(result=None):
        OUTDIR.mkdir(parents=True, exist_ok=True)
        data = {"arch": arch, "pipe": pipe, "seed_ns": seed, "step_ns": STEP,
                "runs": [hist[t] for t in sorted(hist)]}
        if result:
            data.update(result)
        (OUTDIR / f"{arch}.json").write_text(json.dumps(data, indent=2) + "\n")

    def next_from(rec: dict, closing: bool) -> float:
        ws = rec.get("setup_ws_slowest")
        t = rec["period_ns"]
        if ws is None:                       # flow failed: no slack to extrapolate from
            return t + 1.0 if not closing else t - STEP
        est = q_up(t - ws)
        return max(est, t + STEP) if not closing else min(est, t - STEP)

    probe(seed)
    nonmono = []
    for _ in range(MAX_RUNS):
        closing = sorted(t for t, r in hist.items() if r["closes"])
        # A closing T is acceptable unless T + 0.25 was run and failed.
        accepted = []
        for t in closing:
            up = round(t + STEP, 2)
            if up in hist and not hist[up]["closes"]:
                if t not in nonmono:
                    nonmono.append(t)
                continue
            accepted.append(t)
        hi = accepted[0] if accepted else None
        below = [t for t, r in hist.items() if not r["closes"] and (hi is None or t < hi)]
        lo = max(below) if below else None

        if hi is not None and lo is not None and round(hi - lo, 2) <= STEP:
            up = round(hi + STEP, 2)
            if up not in hist:
                probe(up)
                continue
            result = {"min_period_ns": hi, "failing_neighbour_ns": lo, "status": "DONE",
                      "nonmonotonic_points_ns": sorted(nonmono), "runs_used": len(hist),
                      "minutes": round((time.time() - t_start) / 60, 1)}
            save(result)
            print(f"[{arch}] DONE min period {hi} ns ({len(hist)} runs)", flush=True)
            return result | {"arch": arch}
        if hi is None:
            worst_fail = max(t for t in hist if not hist[t]["closes"])
            probe(next_from(hist[worst_fail], closing=False))
        elif lo is None:
            probe(next_from(hist[hi], closing=True))
        else:
            mid = round(round(((lo + hi) / 2) / STEP) * STEP, 2)
            if mid <= lo or mid >= hi:
                mid = round(lo + STEP, 2)
            probe(mid)

    result = {"status": "INCOMPLETE", "reason": f"no answer within {MAX_RUNS} runs",
              "nonmonotonic_points_ns": sorted(nonmono), "runs_used": len(hist)}
    save(result)
    print(f"[{arch}] INCOMPLETE after {len(hist)} runs", flush=True)
    return result | {"arch": arch}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--adder", action="append", choices=list(ADDERS))
    ap.add_argument("--seed", type=float, default=15.0, help="first period to try (ns)")
    ap.add_argument("--pipe", type=int, default=0, choices=[0, 1])
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
    archs = a.adder or list(ADDERS)
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        results = list(ex.map(search, archs, [a.seed] * len(archs), [a.pipe] * len(archs)))
    # Merge every per-architecture file (not only this invocation's) into one log.
    merged = {}
    for f in sorted(OUTDIR.glob("*.json")):
        d = json.loads(f.read_text())
        merged[d["arch"]] = {k: v for k, v in d.items() if k not in ("arch", "runs")} | {
            "runs": [{k: r.get(k) for k in ("period_ns", "status", "setup_ws_slowest", "hold_ws_min",
                                             "run_dir")} for r in d["runs"]]}
    log = {"step_ns": STEP, "criterion": "setup WS >= 0 at max_ss_100C_1v60 and hold WS >= 0 at all corners",
           "results": merged}
    (REPO / "results" / "flow" / "sweep_log.json").write_text(json.dumps(log, indent=2) + "\n")
    for r in results:
        print(f"{r['arch']:<5} {r['status']:<10} min_period={r.get('min_period_ns')} ns "
              f"runs={r['runs_used']} nonmonotonic={r['nonmonotonic_points_ns']}")
    return 0 if all(r["status"] == "DONE" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
