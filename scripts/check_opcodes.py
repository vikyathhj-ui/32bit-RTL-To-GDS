#!/usr/bin/env python3
"""Check that rtl/alu_pkg.sv agrees with the Python side on all shared codes.

1. Opcodes: rtl/alu_pkg.sv OP_* vs model/alu_ref.py OPCODES.
2. Adder codes: rtl/alu_pkg.sv ADDER_* vs scripts/adders.py ADDERS.

The RTL and the golden model are written independently (DECISIONS D-011), so
the one fact they must share, the opcode numbers, is checked here instead of
being generated from one source. Model name "SEXT.B" maps to RTL "OP_SEXT_B".

Exit status 0 when everything matches and the illegal range starts at the
first unused code; 1 otherwise.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "model"))
sys.path.insert(0, str(REPO / "scripts"))

from adders import ADDERS  # noqa: E402
from alu_ref import ILLEGAL_OPCODES, OPCODES  # noqa: E402

PKG = REPO / "rtl" / "alu_pkg.sv"
LINE = re.compile(r"localparam\s+logic\s*\[[^\]]+\]\s*OP_(\w+)\s*=\s*\d+'d(\d+)\s*;")
ADDER_LINE = re.compile(r"localparam\s+int\s+ADDER_(\w+)\s*=\s*(\d+)\s*;")


def main() -> int:
    rtl = {m.group(1): int(m.group(2)) for m in LINE.finditer(PKG.read_text())}
    illegal_min = rtl.pop("ILLEGAL_MIN", None)
    model = {name.replace(".", "_"): code for name, code in OPCODES.items()}

    errors = []
    for name in sorted(set(rtl) | set(model)):
        if name not in rtl:
            errors.append(f"OP_{name} missing from {PKG.name}")
        elif name not in model:
            errors.append(f"OP_{name} is in {PKG.name} but not in the model")
        elif rtl[name] != model[name]:
            errors.append(f"OP_{name}: rtl={rtl[name]} model={model[name]}")
    if illegal_min != min(ILLEGAL_OPCODES):
        errors.append(f"OP_ILLEGAL_MIN={illegal_min}, model's first illegal code is {min(ILLEGAL_OPCODES)}")

    rtl_adders = {m.group(1): int(m.group(2)) for m in ADDER_LINE.finditer(PKG.read_text())}
    if rtl_adders != ADDERS:
        errors.append(f"ADDER codes differ: rtl={rtl_adders} scripts/adders.py={ADDERS}")

    for e in errors:
        print("MISMATCH:", e)
    print(f"check_opcodes: {'PASS' if not errors else 'FAIL'} "
          f"({len(rtl)} opcodes in rtl, {len(model)} in model, illegal from {illegal_min}; "
          f"{len(rtl_adders)} adder codes)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
