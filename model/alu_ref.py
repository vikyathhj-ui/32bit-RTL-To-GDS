"""Golden reference model of the RV32I + Zbb ALU (docs/SPEC.md).

Written from the ratified RISC-V specification text, never from the RTL:
  - RV32I: riscv-isa-manual, "RV32I Base Integer Instruction Set", integer
    register-register operations.
  - Zbb:   riscv-isa-manual src/unpriv/zb.adoc, per-instruction "Operation"
    blocks (anchors cited per function below).

All values are unsigned Python ints in [0, 2**32). Signed views are taken
explicitly with to_signed(). Flags follow docs/SPEC.md section "Flags"
(DECISIONS D-008).

Usage as a CLI:
    python3 model/alu_ref.py ADD 0x7fffffff 1
"""

from __future__ import annotations

import sys
from typing import NamedTuple

XLEN = 32
MASK = (1 << XLEN) - 1
SIGN = 1 << (XLEN - 1)

# Opcode encoding: docs/SPEC.md section "Opcode table" (DECISIONS D-009).
OPCODES: dict[str, int] = {
    "ADD": 0, "SUB": 1, "SLL": 2, "SLT": 3, "SLTU": 4,
    "XOR": 5, "SRL": 6, "SRA": 7, "OR": 8, "AND": 9,
    "MIN": 10, "MAX": 11, "MINU": 12, "MAXU": 13,
    "ANDN": 14, "ORN": 15, "XNOR": 16,
    "ROL": 17, "ROR": 18,
    "CLZ": 19, "CTZ": 20, "CPOP": 21,
    "SEXT.B": 22, "SEXT.H": 23, "ZEXT.H": 24, "REV8": 25, "ORC.B": 26,
}
NAMES: dict[int, str] = {v: k for k, v in OPCODES.items()}
NUM_OPCODES = 1 << 5
ILLEGAL_OPCODES = tuple(c for c in range(NUM_OPCODES) if c not in NAMES)

# Ops that read only operand a (b is ignored).
UNARY_OPS = frozenset({"CLZ", "CTZ", "CPOP", "SEXT.B", "SEXT.H", "ZEXT.H", "REV8", "ORC.B"})


class AluResult(NamedTuple):
    y: int
    n: int
    z: int
    c: int
    v: int
    illegal: int


# ---------------------------------------------------------------- helpers

def to_signed(x: int) -> int:
    """Two's-complement signed value of a 32-bit pattern."""
    x &= MASK
    return x - (1 << XLEN) if x & SIGN else x


def shamt(b: int) -> int:
    """Shift/rotate amount: b[4:0] (RV32I SLL/SRL/SRA, Zbb ROL/ROR)."""
    return b & 0x1F


def sll(a: int, s: int) -> int:
    return (a << s) & MASK


def srl(a: int, s: int) -> int:
    return (a & MASK) >> s


def sra(a: int, s: int) -> int:
    return (to_signed(a) >> s) & MASK  # Python >> on negative ints is arithmetic


def rol(a: int, s: int) -> int:
    """zb.adoc #insns-rol: (rs1 << shamt) | (rs1 >> (xlen - shamt))."""
    s &= 0x1F
    return ((a << s) | (a >> (XLEN - s))) & MASK


def ror(a: int, s: int) -> int:
    """zb.adoc #insns-ror: (rs1 >> shamt) | (rs1 << (xlen - shamt))."""
    s &= 0x1F
    return ((a >> s) | (a << (XLEN - s))) & MASK


def clz(a: int) -> int:
    """zb.adoc #insns-clz: (xlen-1) - HighestSetBit(rs); 32 for 0."""
    for i in range(XLEN - 1, -1, -1):
        if (a >> i) & 1:
            return (XLEN - 1) - i
    return XLEN


def ctz(a: int) -> int:
    """zb.adoc #insns-ctz: LowestSetBit(rs); 32 for 0."""
    for i in range(XLEN):
        if (a >> i) & 1:
            return i
    return XLEN


def cpop(a: int) -> int:
    """zb.adoc #insns-cpop: number of set bits."""
    return sum((a >> i) & 1 for i in range(XLEN))


def sext(a: int, width: int) -> int:
    """EXTS(a[width-1:0]) to 32 bits (zb.adoc #insns-sext_b / #insns-sext_h)."""
    v = a & ((1 << width) - 1)
    if v & (1 << (width - 1)):
        v |= MASK & ~((1 << width) - 1)
    return v


def rev8(a: int) -> int:
    """zb.adoc #insns-rev8: reverse byte order."""
    return int.from_bytes((a & MASK).to_bytes(4, "little"), "big")


def orc_b(a: int) -> int:
    """zb.adoc #insns-orc_b: each byte -> 0xFF if non-zero else 0x00."""
    out = 0
    for i in range(0, XLEN, 8):
        if (a >> i) & 0xFF:
            out |= 0xFF << i
    return out


def bitrev(a: int) -> int:
    """Bit reversal (not an ALU op; used by tests and later by the RTL story)."""
    return int(f"{a & MASK:032b}"[::-1], 2)


def add_with_flags(a: int, b: int, cin: int) -> tuple[int, int, int]:
    """a + b + cin -> (sum, carry_out, signed_overflow)."""
    full = (a & MASK) + (b & MASK) + cin
    s = full & MASK
    c = full >> XLEN
    # Overflow: operands have the same sign and the result's sign differs.
    v = int(((a ^ s) & (b ^ s) & SIGN) != 0)
    return s, c, v


# ---------------------------------------------------------------- the ALU

def alu(op: int, a: int, b: int) -> AluResult:
    """Evaluate one ALU operation. op is the 5-bit opcode; a, b are 32-bit."""
    if not 0 <= op < NUM_OPCODES:
        raise ValueError(f"opcode out of 5-bit range: {op}")
    a &= MASK
    b &= MASK
    name = NAMES.get(op)
    c = v = 0
    illegal = 0

    if name == "ADD":
        y, c, v = add_with_flags(a, b, 0)
    elif name == "SUB":
        # SUB = a + ~b + 1; C is the carry-out ("no borrow"), D-008.
        y, c, v = add_with_flags(a, ~b & MASK, 1)
    elif name == "SLL":
        y = sll(a, shamt(b))
    elif name == "SLT":
        y = int(to_signed(a) < to_signed(b))
    elif name == "SLTU":
        y = int(a < b)
    elif name == "XOR":
        y = a ^ b
    elif name == "SRL":
        y = srl(a, shamt(b))
    elif name == "SRA":
        y = sra(a, shamt(b))
    elif name == "OR":
        y = a | b
    elif name == "AND":
        y = a & b
    elif name == "MIN":
        y = a if to_signed(a) < to_signed(b) else b
    elif name == "MAX":
        y = b if to_signed(a) < to_signed(b) else a
    elif name == "MINU":
        y = a if a < b else b
    elif name == "MAXU":
        y = b if a < b else a
    elif name == "ANDN":
        y = a & ~b & MASK
    elif name == "ORN":
        y = (a | ~b) & MASK
    elif name == "XNOR":
        y = ~(a ^ b) & MASK
    elif name == "ROL":
        y = rol(a, shamt(b))
    elif name == "ROR":
        y = ror(a, shamt(b))
    elif name == "CLZ":
        y = clz(a)
    elif name == "CTZ":
        y = ctz(a)
    elif name == "CPOP":
        y = cpop(a)
    elif name == "SEXT.B":
        y = sext(a, 8)
    elif name == "SEXT.H":
        y = sext(a, 16)
    elif name == "ZEXT.H":
        y = a & 0xFFFF
    elif name == "REV8":
        y = rev8(a)
    elif name == "ORC.B":
        y = orc_b(a)
    else:
        y = 0
        illegal = 1

    n = (y >> (XLEN - 1)) & 1
    z = int(y == 0)
    return AluResult(y, n, z, c, v, illegal)


def alu_by_name(name: str, a: int, b: int = 0) -> AluResult:
    return alu(OPCODES[name.upper()], a, b)


def _main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(__doc__.strip().splitlines()[-1])
        return 2
    name = argv[1].upper()
    op = OPCODES[name] if name in OPCODES else int(name, 0)
    a = int(argv[2], 0)
    b = int(argv[3], 0) if len(argv) == 4 else 0
    r = alu(op, a, b)
    print(f"{NAMES.get(op, 'ILLEGAL')}(0x{a & MASK:08x}, 0x{b & MASK:08x}) = 0x{r.y:08x}  "
          f"N={r.n} Z={r.z} C={r.c} V={r.v} illegal={r.illegal}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
