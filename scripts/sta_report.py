#!/usr/bin/env python3
"""Critical paths of the recommended configuration at every corner (BRIEF A5 STA_REPORT, D-031/D-032).

For each closing run given (default: HC preserved PIPE=0, and PIPE=1 if its
sweep is done), read the post-PnR STA reports (newest *-openroad-stapostpnr/
<corner>/max.rpt and min.rpt) and extract the worst setup and hold path:
start/end flop and the nets they drive/receive, slack, arrival, and the data
path split into launch clock-to-Q, logic cells, plain buffers, delay cells
(clkdlybuf*/dlygate*) and wire delay. The wire delay here is only the RC of
the wire itself (pin to pin); the wire's capacitance slows the *driving* cell
and so appears in that cell's delay. For an input-port startpoint the path is
measured from the port's arrival (clock + external input delay). The worst-path excerpt of
each report is saved next to the JSON, so the evidence stays in the repo.

Run from the repo root (plain Python, no EDA tools needed):
    python3 scripts/sta_report.py          # -> results/sta/<ARCH>_<variant>.json
    python3 scripts/sta_report.py --md     # Markdown tables for docs/STA_REPORT.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "results" / "sta"
TARGETS = {"HC_preserved": REPO / "results" / "flow" / "sweep_preserved" / "HC.json",
           "HC_preserved_P1": REPO / "results" / "flow" / "sweep_preserved_P1" / "HC.json"}
# "<fanout> <cap> <slew> <incr> <time> ^|v <inst>/<pin> (<cell>)", fanout/cap missing on input pins.
PIN = re.compile(r"^\s*(?:(\d+)\s+([\d.]+)\s+)?([\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+[\^v]\s+(\S+)/(\S+)\s+\((\S+)\)")
NET = re.compile(r"^\s+(\S+) \(net\)")
# Input-port startpoint: "<fanout> <cap> <slew> <incr> <time> ^|v <port> (in)"; launch = after the external delay.
PORT = re.compile(r"^\s*(?:\d+\s+[\d.]+\s+)?[\d.]+\s+(-?[\d.]+)\s+(-?[\d.]+)\s+[\^v]\s+(\S+) \(in\)")
OUT_PINS = {"X", "Y", "Q", "Q_N", "SUM", "COUT"}


def first_path(rpt: Path) -> str:
    text = rpt.read_text()
    i = text.find("Startpoint:")
    j = text.find("Startpoint:", i + 1)
    return text[i:j if j > 0 else None].rstrip() + "\n"


def parse(path: str) -> dict:
    sp = re.search(r"Startpoint: (\S+) \(([^)]*)\)", path)
    ep = re.search(r"Endpoint: (\S+) \(([^)]*)\)", path)
    arrival = float(re.search(r"(-?[\d.]+)\s+data arrival time", path).group(1))
    slack = re.search(r"(-?[\d.]+)\s+slack \((MET|VIOLATED)\)", path)
    lines = path.split("data arrival time")[0].splitlines()
    start_inst = sp.group(1)
    split = {"launch_clk_to_q_ns": 0.0, "logic_ns": 0.0, "buffer_ns": 0.0, "delay_cell_ns": 0.0, "wire_ns": 0.0}
    cells, nets, launched, launch_time = [], [], False, None
    for ln in lines:
        if (m := NET.match(ln)) and launched:
            nets.append(m.group(1))
        if (m := PORT.match(ln)) and m.group(3) == start_inst:
            launched, launch_time = True, float(m.group(2)) - float(m.group(1))
            split["wire_ns"] += float(m.group(1))
            continue
        m = PIN.match(ln)
        if not m:
            continue
        incr, time, inst, pin, cell = float(m.group(4)), float(m.group(5)), m.group(6), m.group(7), m.group(8)
        cell = cell.replace("sky130_fd_sc_hd__", "")
        if inst == start_inst and pin in OUT_PINS and not launched:
            launched, launch_time = True, time - incr
            split["launch_clk_to_q_ns"] += incr
            continue
        if not launched:
            continue                                   # clock tree up to the launch flop
        if pin not in OUT_PINS:
            split["wire_ns"] += incr
            continue
        kind = ("delay_cell_ns" if re.match(r"(clkdlybuf|dlygate|dlymetal)", cell)
                else "buffer_ns" if re.match(r"(buf|clkbuf)_", cell) else "logic_ns")
        split[kind] += incr
        cells.append({"inst": inst, "cell": cell, "delay_ns": incr, "fanout": int(m.group(1) or 0)})
    return {"startpoint": sp.group(1), "startpoint_type": sp.group(2), "start_net": nets[0] if nets else None,
            "endpoint": ep.group(1), "endpoint_type": ep.group(2), "end_net": nets[-1] if nets else None,
            "data_arrival_ns": arrival, "launch_clock_arrival_ns": launch_time,
            "slack_ns": float(slack.group(1)) if slack else None,
            "data_path_ns": round(arrival - launch_time, 6) if launch_time is not None else None,
            "split_ns": {k: round(v, 4) for k, v in split.items()},
            "logic_depth": sum(1 for c in cells if not re.match(r"(clkdlybuf|dlygate|dlymetal|buf_|clkbuf_)", c["cell"])),
            "cells_on_path": len(cells), "cells": cells}


def one(name: str, sweep_file: Path) -> dict | None:
    if not sweep_file.exists():
        return None
    sweep = json.loads(sweep_file.read_text())
    if sweep.get("status") != "DONE":
        print(f"skip {name}: sweep {sweep.get('status') or 'RUNNING'}")
        return None
    T = sweep["min_period_ns"]
    run = REPO / next(r["run_dir"] for r in sweep["runs"] if r["period_ns"] == T)
    sta = sorted(run.glob("*-openroad-stapostpnr"), key=lambda p: int(p.name.split("-")[0]))[-1]
    m = json.loads((run / "final" / "metrics.json").read_text())
    keep = OUT / name
    keep.mkdir(parents=True, exist_ok=True)
    corners = {}
    for cdir in sorted(p for p in sta.iterdir() if p.is_dir()):
        c = cdir.name
        rec = {"setup_ws_ns": m.get(f"timing__setup__ws__corner:{c}"),
               "setup_tns_ns": m.get(f"timing__setup__tns__corner:{c}"),
               "hold_ws_ns": m.get(f"timing__hold__ws__corner:{c}"),
               "hold_tns_ns": m.get(f"timing__hold__tns__corner:{c}")}
        for kind, rpt in (("setup", "max.rpt"), ("hold", "min.rpt")):
            excerpt = first_path(cdir / rpt)
            (keep / f"{c}.{kind}.rpt").write_text(excerpt)
            rec[f"{kind}_path"] = parse(excerpt) | {"source": str((keep / f"{c}.{kind}.rpt").relative_to(REPO))}
        rec["fmax_MHz"] = round(1000.0 / (T - rec["setup_ws_ns"]), 2)
        corners[c] = rec
    pipe = int(next(p.split("=")[1] for p in json.loads((run / "resolved.json").read_text())["SYNTH_PARAMETERS"]
                    if p.startswith("PIPE=")))
    return {"name": name, "run": str(run.relative_to(REPO)), "period_ns": T, "pipe": pipe, "latency_cycles": 2 + pipe,
            "sta_step": str(sta.relative_to(REPO)), "corners": corners}


CORNER_ORDER = [f"{rc}_{pvt}" for pvt in ("ss_100C_1v60", "tt_025C_1v80", "ff_n40C_1v95") for rc in ("max", "nom", "min")]


def markdown(r: dict) -> str:
    """Tables for docs/STA_REPORT.md (pasted, never hand-typed)."""
    out = [f"**{r['name']}** — T = {r['period_ns']} ns, PIPE={r['pipe']}, latency {r['latency_cycles']} cycles",
           "", "| Corner | Setup WS (ns) | Setup TNS | fmax (MHz) | Worst setup path | Logic cells | Data path (ns) | "
           "Logic / delay cells / buffers / clk→Q (ns) | Hold WS (ns) | Worst hold path |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for c in CORNER_ORDER:
        v = r["corners"][c]
        s, h, sp = v["setup_path"], v["hold_path"], v["setup_path"]["split_ns"]
        out.append(f"| {c} | {v['setup_ws_ns']:.4f} | {v['setup_tns_ns']} | {v['fmax_MHz']} | "
                   f"`{s['start_net']}` → `{s['end_net']}` | {s['logic_depth']} | {s['data_path_ns']:.3f} | "
                   f"{sp['logic_ns']:.2f} / {sp['delay_cell_ns']:.2f} / {sp['buffer_ns']:.2f} / "
                   f"{sp['launch_clk_to_q_ns']:.2f} | {v['hold_ws_ns']:.4f} | `{h['start_net']}` → `{h['end_net']}` |")
    worst = r["corners"]["max_ss_100C_1v60"]["setup_path"]
    out += ["", f"Cells on the worst `max_ss_100C_1v60` setup path ({worst['source']}):", "",
            "| # | Instance | Cell | Fan-out | Delay (ns) |", "|---|---|---|---|---|"]
    out += [f"| {i} | {c['inst']} | {c['cell']} | {c['fanout']} | {c['delay_ns']:.3f} |"
            for i, c in enumerate(worst["cells"], 1)]
    return "\n".join(out)


def main() -> int:
    if "--md" in sys.argv:
        for name in TARGETS:
            f = OUT / f"{name}.json"
            if f.exists():
                print(markdown(json.loads(f.read_text())), "\n")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, f in TARGETS.items():
        r = one(name, f)
        if r is None:
            continue
        (OUT / f"{name}.json").write_text(json.dumps(r, indent=2) + "\n")
        print(f"{name}: T={r['period_ns']} PIPE={r['pipe']}")
        for c, v in r["corners"].items():
            s, h = v["setup_path"], v["hold_path"]
            print(f"  {c:<18} setup WS {v['setup_ws_ns']:+.4f} {s['start_net']}->{s['end_net']} depth {s['logic_depth']} "
                  f"split {s['split_ns']} | hold WS {v['hold_ws_ns']:+.4f} {h['start_net']}->{h['end_net']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
