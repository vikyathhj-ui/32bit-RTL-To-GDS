"""Functional coverage model for alu_top (BRIEF A3, docs/COVERAGE.md).

Built on cocotb-coverage. Every checked result is passed to sample(). Bins that
are unreachable by the specification are left out of the bin lists and
recorded in IGNORED with the reason; docs/COVERAGE.md explains each one.

Coverage points:
  op_x_a_class   (op, class of a)   for all 27 ops + ILLEGAL
  op_x_b_class   (op, class of b)   for binary ops only (unary ops ignore b)
  op_x_flag      (op, flag, value)  N/Z/C/V x {0,1}
  shift_amount   (op, amount bin)   SLL/SRL/SRA/ROL/ROR x {0, 1, 2-15, 16-30, 31}
  clz_result     0..32
  ctz_result     0..32
"""

from __future__ import annotations

import json
from pathlib import Path

from cocotb_coverage.coverage import CoverPoint, coverage_db

from alu_ref import ILLEGAL_OPCODES, NAMES, OPCODES, UNARY_OPS

INT_MIN = 0x80000000
INT_MAX = 0x7FFFFFFF

OP_NAMES = list(OPCODES) + ["ILLEGAL"]
BINARY_OPS = [n for n in OPCODES if n not in UNARY_OPS] + ["ILLEGAL"]
CLASSES = ["zero", "positive", "negative", "max", "min"]
FLAGS = ["N", "Z", "C", "V"]
SHIFT_OPS = ["SLL", "SRL", "SRA", "ROL", "ROR"]
SHIFT_BINS = ["0", "1", "2-15", "16-30", "31"]

# Results that can never be negative (N=1 unreachable): 0/1 results, counts <= 32,
# a zero-extended halfword, and illegal opcodes (y = 0).
NEVER_NEGATIVE = {"SLT", "SLTU", "CLZ", "CTZ", "CPOP", "ZEXT.H", "ILLEGAL"}

IGNORED: dict[str, list[dict]] = {"op_x_b_class": [], "op_x_flag": []}


def op_name(op: int) -> str:
    return "ILLEGAL" if op in ILLEGAL_OPCODES else NAMES[op]


def operand_class(x: int) -> str:
    if x == 0:
        return "zero"
    if x == INT_MAX:
        return "max"
    if x == INT_MIN:
        return "min"
    return "negative" if x & INT_MIN else "positive"


def shift_bin(b: int) -> str:
    s = b & 31
    return "0" if s == 0 else "1" if s == 1 else "31" if s == 31 else "2-15" if s < 16 else "16-30"


def _flag_bins() -> list[tuple[str, str, int]]:
    bins = []
    for op in OP_NAMES:
        for flag in FLAGS:
            for val in (0, 1):
                reason = None
                if flag in ("C", "V") and val == 1 and op not in ("ADD", "SUB"):
                    reason = "SPEC section 4: C and V are 0 for every op except ADD/SUB"
                elif flag == "N" and val == 1 and op in NEVER_NEGATIVE:
                    reason = "result is 0/1, a count <= 32, a zero-extended halfword, or 0 (illegal)"
                elif flag == "Z" and val == 0 and op == "ILLEGAL":
                    reason = "SPEC section 5: illegal opcodes give y = 0, so Z is always 1"
                if reason:
                    IGNORED["op_x_flag"].append({"bin": [op, flag, val], "reason": reason})
                else:
                    bins.append((op, flag, val))
    return bins


def _b_class_bins() -> list[tuple[str, str]]:
    for op in UNARY_OPS:
        IGNORED["op_x_b_class"].append(
            {"bin": [op, "*"], "reason": "unary op: b is ignored (SPEC section 3)"})
    return [(op, c) for op in BINARY_OPS for c in CLASSES]


FLAG_BINS = _flag_bins()
B_CLASS_BINS = _b_class_bins()


@CoverPoint("alu.op_x_a_class", xf=lambda op, a, b, r: (op_name(op), operand_class(a)),
            bins=[(op, c) for op in OP_NAMES for c in CLASSES])
@CoverPoint("alu.op_x_b_class", xf=lambda op, a, b, r: (op_name(op), operand_class(b)),
            bins=B_CLASS_BINS)
@CoverPoint("alu.shift_amount", xf=lambda op, a, b, r: (op_name(op), shift_bin(b)),
            bins=[(op, s) for op in SHIFT_OPS for s in SHIFT_BINS])
@CoverPoint("alu.clz_result", xf=lambda op, a, b, r: r.y if op == OPCODES["CLZ"] else None,
            bins=list(range(33)))
@CoverPoint("alu.ctz_result", xf=lambda op, a, b, r: r.y if op == OPCODES["CTZ"] else None,
            bins=list(range(33)))
def _sample_main(op, a, b, r):
    pass


# Flags are four separate samples per result (one per flag), so they need their own function.
@CoverPoint("alu.op_x_flag", xf=lambda op, flag, val: (op_name(op), flag, val), bins=FLAG_BINS)
def _sample_flag(op, flag, val):
    pass


def sample(op: int, a: int, b: int, r) -> None:
    """Record one checked result (r is an alu_ref.AluResult)."""
    _sample_main(op, a, b, r)
    _sample_flag(op, "N", r.n)
    _sample_flag(op, "Z", r.z)
    _sample_flag(op, "C", r.c)
    _sample_flag(op, "V", r.v)


def report(path: Path) -> dict:
    """Write coverage (per point: size, hits, %, missed bins, ignored bins) to JSON + YAML."""
    points = {}
    for name in ("op_x_a_class", "op_x_b_class", "op_x_flag", "shift_amount", "clz_result", "ctz_result"):
        cp = coverage_db[f"alu.{name}"]
        missed = [list(k) if isinstance(k, tuple) else k for k, hits in cp.detailed_coverage.items() if hits == 0]
        points[name] = {
            "bins": cp.size,
            "covered": cp.coverage,
            "percent": round(100.0 * cp.coverage / cp.size, 2) if cp.size else 100.0,
            "missed": missed,
            "ignored": IGNORED.get(name, []),
        }
    total_bins = sum(p["bins"] for p in points.values())
    total_cov = sum(p["covered"] for p in points.values())
    summary = {"bins": total_bins, "covered": total_cov,
               "percent": round(100.0 * total_cov / total_bins, 2), "points": points}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n")
    coverage_db.export_to_yaml(str(path.with_suffix(".yml")))
    return summary
