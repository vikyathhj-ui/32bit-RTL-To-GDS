#!/usr/bin/env python3
"""Signoff evidence for the recommended configuration (BRIEF A4/A6, DECISIONS D-031).

The LibreLane run already contains the signoff steps. This script:
  1. reads their counts from the run's final/metrics.json and the step reports
     (Magic DRC, KLayout DRC, KLayout XOR, Netgen LVS, antenna);
  2. copies the reports into results/signoff/<ARCH>_<variant>/;
  3. runs IR drop again with *real* activity: OpenROAD reads the final ODB,
     SDC and nominal SPEF plus the gate-level workload VCD (D-025), then
     analyze_power_grid on VPWR and VGND. LibreLane's own IR-drop step uses
     default activity; both results are recorded, each labelled;
  4. renders the final GDS with KLayout at 2400 px (LibreLane's render.py);
  5. writes signoff.json. Exit 0 only if every count is 0 and LVS matches.

Run inside the iic-osic container from the repo root, after power_all.py:
    python3 scripts/signoff.py [--arch HC] [--variant preserved]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PDK = Path(os.environ.get("PDK_ROOT", "/foss/pdks")) / "sky130A"
LIB = PDK / "libs.ref" / "sky130_fd_sc_hd" / "lib" / "sky130_fd_sc_hd__tt_025C_1v80.lib"
KL = PDK / "libs.tech" / "klayout" / "tech"
RENDER = Path("/usr/local/lib/python3.12/dist-packages/librelane/scripts/klayout/render.py")
SWEEPS = {"default": REPO / "results" / "flow" / "sweep", "preserved": REPO / "results" / "flow" / "sweep_preserved"}
IR_FIELDS = {"total_power_W": r"Total power\s*:\s*(\S+)", "worst_voltage_V": r"Worstcase voltage:\s*(\S+)",
             "avg_drop_V": r"Average IR drop\s*:\s*(\S+)", "worst_drop_V": r"Worstcase IR drop:\s*(\S+)",
             "percent_drop": r"Percentage drop\s*:\s*(\S+)\s*%"}


def step(run: Path, suffix: str) -> Path:
    """Newest step directory with this suffix (a repeated run appends a second set, D-030)."""
    return sorted(run.glob(f"*-{suffix}"), key=lambda p: int(p.name.split("-")[0]))[-1]


def rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def ir_blocks(text: str) -> dict:
    out = {}
    for block in text.split("########## IR report #################")[1:]:
        net = re.search(r"Net\s*:\s*(\S+)", block).group(1)
        out[net] = {k: float(m.group(1)) for k, pat in IR_FIELDS.items() if (m := re.search(pat, block))}
    return out


def ir_with_vcd(run: Path, vcd: Path, work: Path) -> dict:
    tcl = work / "irdrop_vcd.tcl"
    tcl.write_text("\n".join([
        f"read_liberty {LIB}",
        f"read_db {run / 'final' / 'odb' / 'alu_top.odb'}",
        f"read_sdc {run / 'final' / 'sdc' / 'alu_top.sdc'}",
        f"read_spef {run / 'final' / 'spef' / 'nom' / 'alu_top.nom.spef'}",
        "set_propagated_clock [all_clocks]",
        f"read_vcd -scope alu_top {vcd}",
        "report_activity_annotation",
        "report_power -digits 6",
        "set_pdnsim_net_voltage -net VPWR -voltage 1.8",
        f"analyze_power_grid -net VPWR -voltage_file {work / 'net-VPWR.csv'}",
        "set_pdnsim_net_voltage -net VGND -voltage 0",
        f"analyze_power_grid -net VGND -voltage_file {work / 'net-VGND.csv'}",
    ]) + "\n")
    p = subprocess.run(["openroad", "-exit", "-no_splash", str(tcl)], capture_output=True, text=True)
    log = "\n".join(l for l in (p.stdout + p.stderr).splitlines() if "STA-1173" not in l and "Warning 198" not in l)
    (work / "irdrop_vcd.rpt").write_text(log + "\n")
    ann = {k: int(m.group(1)) for k in ("vcd", "unannotated") if (m := re.search(rf"^\s*{k}\s+(\d+)", log, re.M))}
    return {"label": "activity from the gate-level workload VCD (D-025), tt_025C_1v80, nominal SPEF",
            "annotation": ann, "nets": ir_blocks(log), "exit": p.returncode, "report": rel(work / "irdrop_vcd.rpt")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arch", default="HC")
    ap.add_argument("--variant", default="preserved", choices=list(SWEEPS))
    a = ap.parse_args(argv)
    sweep = json.loads((SWEEPS[a.variant] / f"{a.arch}.json").read_text())
    T = sweep["min_period_ns"]
    run = REPO / next(r["run_dir"] for r in sweep["runs"] if r["period_ns"] == T)
    out = REPO / "results" / "signoff" / f"{a.arch}_{a.variant}"
    out.mkdir(parents=True, exist_ok=True)
    m = json.loads((run / "final" / "metrics.json").read_text())

    copies = {
        "drc.magic.rpt": step(run, "magic-drc") / "reports" / "drc.magic.rpt",
        "drc.klayout.lyrdb": step(run, "klayout-drc") / "reports" / "drc.klayout.lyrdb",
        "lvs.netgen.rpt": step(run, "netgen-lvs") / "reports" / "lvs.netgen.rpt",
        "antenna_summary.rpt": step(run, "openroad-checkantennas-1") / "reports" / "antenna_summary.rpt",
        "xor.xml": step(run, "klayout-xor") / "xor.xml",
        "irdrop_default_activity.rpt": step(run, "openroad-irdropreport") / "irdrop.rpt",
        "render_librelane_1000px.png": run / "final" / "render" / "alu_top.png",
    }
    for name, src in copies.items():
        shutil.copy(src, out / name)

    lvs_text = (out / "lvs.netgen.rpt").read_text()
    checks = {
        "magic_drc_errors": m.get("magic__drc_error__count"),
        "klayout_drc_errors": m.get("klayout__drc_error__count"),
        "klayout_xor_differences": m.get("design__xor_difference__count"),
        "lvs_errors": m.get("design__lvs_error__count"),
        "antenna_violating_nets": m.get("antenna__violating__nets"),
        "antenna_violating_pins": m.get("antenna__violating__pins"),
        "route_drc_errors": m.get("route__drc_errors"),
    }
    lvs_match = "Final result: Circuits match uniquely." in lvs_text

    vcd = REPO / "sim_build" / "gls" / run.name / "workload.vcd"
    ir_vcd = ir_with_vcd(run, vcd, out) if vcd.exists() else {"error": f"missing {rel(vcd)}; run power_all.py"}
    ir_default = {"label": "LibreLane OpenROAD.IRDropReport, default activity (not annotated)",
                  "nets": ir_blocks((out / "irdrop_default_activity.rpt").read_text()),
                  "report": rel(out / "irdrop_default_activity.rpt")}

    png = out / "render_2400px.png"
    r = subprocess.run([sys.executable, str(RENDER), str(run / "final" / "gds" / "alu_top.gds"),
                        "--output", str(png), "--resolution", "2400", "--background-color", "white",
                        "-T", str(KL / "sky130A.lyt"), "-P", str(KL / "sky130A.lyp"), "-M", str(KL / "sky130A.map")],
                       capture_output=True, text=True)

    ok = (all(v == 0 for v in checks.values()) and lvs_match and ir_vcd.get("exit") == 0
          and ir_vcd.get("annotation", {}).get("unannotated") == 0 and png.exists())
    rec = {"status": "PASS" if ok else "FAIL", "arch": a.arch, "variant": a.variant, "period_ns": T,
           "run": rel(run), "checks": checks, "lvs_final_result_match": lvs_match,
           "checks_source": rel(run / "final" / "metrics.json"),
           "ir_drop": {"vcd_activity": ir_vcd, "default_activity": ir_default},
           "render": {"png": rel(png) if png.exists() else None, "exit": r.returncode,
                      "librelane_png": rel(out / "render_librelane_1000px.png")},
           "reports": {k: rel(out / k) for k in copies}}
    (out / "signoff.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("status", "checks", "lvs_final_result_match")}, indent=2))
    for net, v in ir_vcd.get("nets", {}).items():
        print(f"IR (VCD) {net}: worst drop {v.get('worst_drop_V')} V, avg {v.get('avg_drop_V')} V, "
              f"{v.get('percent_drop')}%")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
