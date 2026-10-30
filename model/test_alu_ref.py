"""Unit tests for model/alu_ref.py.

Expected values are computed by hand from the ratified definitions (cited per
group), not by calling the model. Spec sources:
  RV32I: riscv-isa-manual, RV32I integer register-register operations.
  Zbb:   riscv-isa-manual src/unpriv/zb.adoc (#insns-* anchors) and
         src/unpriv/bitmanip-examples.adoc (strlen / strcmp).
Flags: docs/SPEC.md "Flags" (DECISIONS D-008).
"""

import random

import pytest

from alu_ref import (
    ILLEGAL_OPCODES, MASK, NAMES, OPCODES, UNARY_OPS,
    alu, alu_by_name, bitrev, clz, cpop, ctz, orc_b, rev8, rol, ror,
)

INT_MIN = 0x80000000
INT_MAX = 0x7FFFFFFF
M1 = 0xFFFFFFFF  # -1
AA = 0xAAAAAAAA
FIVES = 0x55555555

# (op, a, b, y) -- hand-computed results. b is ignored for unary ops.
VECTORS = [
    # ---- RV32I ADD/SUB (y only; flags tested separately)
    ("ADD", 5, 7, 12),
    ("ADD", M1, 1, 0),
    ("ADD", INT_MAX, 1, INT_MIN),
    ("ADD", INT_MIN, INT_MIN, 0),
    ("SUB", 5, 5, 0),
    ("SUB", 3, 5, 0xFFFFFFFE),
    ("SUB", INT_MIN, 1, INT_MAX),
    ("SUB", 0, INT_MIN, INT_MIN),
    # ---- SLL/SRL/SRA: shift amount is b[4:0]; 32 -> 0, 33 -> 1, 36 -> 4
    ("SLL", 1, 0, 1),
    ("SLL", 1, 31, INT_MIN),
    ("SLL", 0x80000001, 1, 2),
    ("SLL", 1, 32, 1),
    ("SLL", 1, 33, 2),
    ("SRL", INT_MIN, 31, 1),
    ("SRL", INT_MIN, 1, 0x40000000),
    ("SRL", M1, 0, M1),
    ("SRL", 0xF0, 36, 0x0F),
    ("SRA", INT_MIN, 31, M1),
    ("SRA", INT_MIN, 1, 0xC0000000),
    ("SRA", INT_MAX, 31, 0),
    ("SRA", 0xFFFFFFF0, 4, M1),
    # ---- SLT/SLTU
    ("SLT", M1, 0, 1),
    ("SLT", 0, M1, 0),
    ("SLT", INT_MIN, INT_MAX, 1),
    ("SLT", 5, 5, 0),
    ("SLTU", M1, 0, 0),
    ("SLTU", 0, M1, 1),
    ("SLTU", INT_MIN, INT_MAX, 0),
    ("SLTU", 4, 5, 1),
    # ---- logic
    ("XOR", AA, FIVES, M1),
    ("XOR", 0x12345678, 0x12345678, 0),
    ("XOR", 0xFF00FF00, 0x0FF00FF0, 0xF0F0F0F0),
    ("XOR", 0, 0, 0),
    ("OR", AA, FIVES, M1),
    ("OR", 0, 0, 0),
    ("OR", 0x0000FFFF, 0xFF000000, 0xFF00FFFF),
    ("OR", INT_MIN, 1, 0x80000001),
    ("AND", AA, FIVES, 0),
    ("AND", M1, 0x12345678, 0x12345678),
    ("AND", 0xF0F0F0F0, 0xFF00FF00, 0xF000F000),
    ("AND", 0, M1, 0),
    # ---- Zbb min/max (zb.adoc #insns-min/max/minu/maxu)
    ("MIN", M1, 1, M1),
    ("MIN", INT_MIN, INT_MAX, INT_MIN),
    ("MIN", 3, 3, 3),
    ("MIN", 2, 7, 2),
    ("MAX", M1, 1, 1),
    ("MAX", INT_MIN, INT_MAX, INT_MAX),
    ("MAX", 2, 7, 7),
    ("MAX", 0, 0xFFFFFFFB, 0),
    ("MINU", M1, 1, 1),
    ("MINU", INT_MIN, INT_MAX, INT_MAX),
    ("MINU", 0, M1, 0),
    ("MINU", 9, 9, 9),
    ("MAXU", M1, 1, M1),
    ("MAXU", INT_MIN, INT_MAX, INT_MIN),
    ("MAXU", 0, 0, 0),
    ("MAXU", 3, 8, 8),
    # ---- Zbb logical with negate (zb.adoc #insns-andn/orn/xnor)
    ("ANDN", M1, 0x0000FFFF, 0xFFFF0000),
    ("ANDN", AA, AA, 0),
    ("ANDN", 0x12345678, 0, 0x12345678),
    ("ANDN", 0, M1, 0),
    ("ORN", 0, 0, M1),
    ("ORN", 0, M1, 0),
    ("ORN", 0x0000FF00, 0xFFFF00FF, 0x0000FF00),
    ("ORN", AA, AA, M1),
    ("XNOR", AA, FIVES, 0),
    ("XNOR", 0x12345678, 0x12345678, M1),
    ("XNOR", 0xF0F0F0F0, 0xFF00FF00, 0xF00FF00F),
    ("XNOR", 0, 0, M1),
    # ---- Zbb rotate (zb.adoc #insns-rol/ror): amount is b[4:0]
    ("ROL", 0x80000001, 0, 0x80000001),
    ("ROL", 0x80000001, 1, 0x00000003),
    ("ROL", 0x80000001, 31, 0xC0000000),
    ("ROL", 0x12345678, 4, 0x23456781),
    ("ROL", 0x12345678, 36, 0x23456781),
    ("ROR", 0x00000003, 1, 0x80000001),
    ("ROR", 0x12345678, 4, 0x81234567),
    ("ROR", 0x12345678, 0, 0x12345678),
    ("ROR", 1, 31, 2),
    # ---- Zbb count (zb.adoc #insns-clz/ctz/cpop): 32 for input 0
    ("CLZ", 0, 0, 32),
    ("CLZ", 1, 0, 31),
    ("CLZ", INT_MIN, 0, 0),
    ("CLZ", 0x00010000, 0, 15),
    ("CLZ", 0x00008000, 0, 16),
    ("CLZ", M1, 0, 0),
    ("CTZ", 0, 0, 32),
    ("CTZ", 1, 0, 0),
    ("CTZ", INT_MIN, 0, 31),
    ("CTZ", 0x00010000, 0, 16),
    ("CTZ", 0xFFFFFFFE, 0, 1),
    ("CPOP", 0, 0, 0),
    ("CPOP", M1, 0, 32),
    ("CPOP", AA, 0, 16),
    ("CPOP", 0xF000000F, 0, 8),
    ("CPOP", 1, 0, 1),
    # ---- Zbb sign/zero extension (zb.adoc #insns-sext_b/sext_h/zext_h)
    ("SEXT.B", 0x80, 0, 0xFFFFFF80),
    ("SEXT.B", 0x7F, 0, 0x7F),
    ("SEXT.B", 0x12345680, 0, 0xFFFFFF80),
    ("SEXT.B", 0xFFFFFF01, 0, 0x01),
    ("SEXT.H", 0x8000, 0, 0xFFFF8000),
    ("SEXT.H", 0x7FFF, 0, 0x7FFF),
    ("SEXT.H", 0x1234ABCD, 0, 0xFFFFABCD),
    ("SEXT.H", 0xFFFF1234, 0, 0x1234),
    ("ZEXT.H", M1, 0, 0xFFFF),
    ("ZEXT.H", 0x12348000, 0, 0x8000),
    ("ZEXT.H", 0, 0, 0),
    ("ZEXT.H", 0xFFFF0000, 0, 0),
    # ---- Zbb byte ops (zb.adoc #insns-rev8, #insns-orc_b)
    ("REV8", 0x12345678, 0, 0x78563412),
    ("REV8", 0xFF000000, 0, 0x000000FF),
    ("REV8", 0x01020304, 0, 0x04030201),
    ("REV8", 0, 0, 0),
    ("ORC.B", 0, 0, 0),
    ("ORC.B", 0x01000100, 0, 0xFF00FF00),
    ("ORC.B", 0x80402010, 0, M1),
    ("ORC.B", 0x00FF0000, 0, 0x00FF0000),
    ("ORC.B", 0x12003400, 0, 0xFF00FF00),
]


@pytest.mark.parametrize("name,a,b,y", VECTORS, ids=lambda v: v if isinstance(v, str) else None)
def test_vector(name, a, b, y):
    assert alu_by_name(name, a, b).y == y


def test_every_op_has_at_least_four_vectors():
    counts = {name: 0 for name in OPCODES}
    for name, *_ in VECTORS:
        counts[name] += 1
    assert all(c >= 4 for c in counts.values()), counts


def test_opcode_table():
    assert len(OPCODES) == 27
    assert sorted(OPCODES.values()) == list(range(27))
    assert ILLEGAL_OPCODES == (27, 28, 29, 30, 31)


@pytest.mark.parametrize("name", sorted(UNARY_OPS))
def test_unary_ops_ignore_b(name):
    for a in (0, 1, 0x12345678, INT_MIN, M1):
        assert alu_by_name(name, a, 0) == alu_by_name(name, a, 0xDEADBEEF)


# ---------------------------------------------------------------- flags (D-008)
# (op, a, b, y, N, Z, C, V)
FLAG_VECTORS = [
    ("ADD", 0, 0, 0, 0, 1, 0, 0),                 # zero result
    ("ADD", M1, 1, 0, 0, 1, 1, 0),                # carry, no overflow
    ("ADD", INT_MAX, 1, INT_MIN, 1, 0, 0, 1),     # overflow, no carry
    ("ADD", INT_MIN, INT_MIN, 0, 0, 1, 1, 1),     # carry and overflow
    ("ADD", 5, 7, 12, 0, 0, 0, 0),
    ("SUB", 5, 5, 0, 0, 1, 1, 0),                 # equal: no borrow -> C=1
    ("SUB", 3, 5, 0xFFFFFFFE, 1, 0, 0, 0),        # borrow -> C=0
    ("SUB", INT_MIN, 1, INT_MAX, 0, 0, 1, 1),     # INT_MIN - 1 overflows
    ("SUB", INT_MAX, M1, INT_MIN, 1, 0, 0, 1),    # INT_MAX - (-1) overflows, borrow
    ("SUB", 0, INT_MIN, INT_MIN, 1, 0, 0, 1),     # 0 - INT_MIN overflows
    ("SUB", M1, 1, 0xFFFFFFFE, 1, 0, 1, 0),       # unsigned a >= b -> C=1
    # other ops: N,Z from y; C=V=0 even where the adder is used internally
    ("SLT", M1, 0, 1, 0, 0, 0, 0),
    ("SLTU", 5, 3, 0, 0, 1, 0, 0),
    ("MIN", INT_MIN, 1, INT_MIN, 1, 0, 0, 0),
    ("MAXU", INT_MIN, 1, INT_MIN, 1, 0, 0, 0),
    ("AND", AA, FIVES, 0, 0, 1, 0, 0),
    ("SRA", INT_MIN, 4, 0xF8000000, 1, 0, 0, 0),
    ("CLZ", 0, 0, 32, 0, 0, 0, 0),
    ("CPOP", 0, 0, 0, 0, 1, 0, 0),
    ("REV8", 0x00000080, 0, 0x80000000, 1, 0, 0, 0),
]


@pytest.mark.parametrize("name,a,b,y,n,z,c,v", FLAG_VECTORS)
def test_flags(name, a, b, y, n, z, c, v):
    r = alu_by_name(name, a, b)
    assert (r.y, r.n, r.z, r.c, r.v, r.illegal) == (y, n, z, c, v, 0)


def test_c_v_zero_for_non_add_sub():
    rng = random.Random(1)
    for name, op in OPCODES.items():
        if name in ("ADD", "SUB"):
            continue
        for _ in range(200):
            r = alu(op, rng.getrandbits(32), rng.getrandbits(32))
            assert (r.c, r.v) == (0, 0), name
            assert r.n == (r.y >> 31) and r.z == int(r.y == 0), name


@pytest.mark.parametrize("op", ILLEGAL_OPCODES)
def test_illegal_opcodes(op):
    for a, b in ((0, 0), (M1, M1), (0x12345678, 0x9ABCDEF0)):
        r = alu(op, a, b)
        assert (r.y, r.n, r.z, r.c, r.v, r.illegal) == (0, 0, 1, 0, 0, 1)


def test_legal_opcodes_not_illegal():
    assert all(alu(op, 1, 2).illegal == 0 for op in NAMES)


def test_opcode_range_checked():
    with pytest.raises(ValueError):
        alu(32, 0, 0)


# ---------------------------------------------------------------- spec examples
# bitmanip-examples.adoc `strlen`: on little-endian, ~orc.b(chunk) has 0xFF in
# NUL byte positions; ctz(...) >> 3 is the index of the first NUL byte.
@pytest.mark.parametrize("chunk,first_nul", [
    (b"ab\x00c", 2), (b"\x00bcd", 0), (b"abc\x00", 3), (b"a\x00\x00\x00", 1),
])
def test_strlen_idiom(chunk, first_nul):
    w = int.from_bytes(chunk, "little")
    inv = ~alu_by_name("ORC.B", w).y & MASK
    assert alu_by_name("CTZ", inv).y >> 3 == first_nul


def test_strlen_idiom_no_nul():
    # A chunk with no NUL byte gives orc.b == all ones (strcmp's `bne t0, t2` test).
    assert alu_by_name("ORC.B", int.from_bytes(b"abcd", "little")).y == M1
    # ...and ~orc.b == 0, so ctz returns 32 -> 32 >> 3 == 4 == "no NUL in 4 bytes".
    assert alu_by_name("CTZ", 0).y >> 3 == 4


# bitmanip-examples.adoc `strcmp`: on little-endian, rev8 puts bytes in
# big-endian order so that SLTU on words matches lexicographic byte order.
def test_strcmp_idiom():
    rng = random.Random(7)
    pairs = [(b"abcd", b"abce"), (b"abce", b"abcd"), (b"b\x01\x01\x01", b"a\xff\xff\xff")]
    pairs += [(bytes(rng.randrange(1, 256) for _ in range(4)),
               bytes(rng.randrange(1, 256) for _ in range(4))) for _ in range(500)]
    for s1, s2 in pairs:
        w1, w2 = int.from_bytes(s1, "little"), int.from_bytes(s2, "little")
        lt = alu_by_name("SLTU", alu_by_name("REV8", w1).y, alu_by_name("REV8", w2).y).y
        assert lt == int(s1 < s2), (s1, s2)


# ---------------------------------------------------------------- properties
def _rand_words(n, seed):
    rng = random.Random(seed)
    corners = [0, 1, M1, INT_MIN, INT_MAX, AA, FIVES]
    return corners + [rng.getrandbits(32) for _ in range(n)]


def _signed(x):
    return x - (1 << 32) if x & INT_MIN else x


def test_properties_unary():
    for x in _rand_words(2000, 11):
        assert ctz(x) == clz(bitrev(x))
        assert cpop(x) + cpop(~x & MASK) == 32
        assert rev8(rev8(x)) == x
        assert orc_b(x) == orc_b(orc_b(x))
        assert alu_by_name("SEXT.B", x).y == (_signed((x & 0xFF) << 24) >> 24) & MASK


def test_properties_binary():
    rng = random.Random(12)
    words = _rand_words(1000, 13)
    for a in words:
        b = rng.getrandbits(32)
        s = b & 31
        assert rol(ror(a, s), s) == a
        assert ror(a, s) == rol(a, (32 - s) & 31)
        assert alu_by_name("ADD", a, b).y == (a + b) & MASK
        sub = alu_by_name("SUB", a, b)
        assert sub.y == (a - b) & MASK
        assert sub.c == int(a >= b)                      # C = no borrow
        assert alu_by_name("SLT", a, b).y == int(_signed(a) < _signed(b))
        assert alu_by_name("MIN", a, b).y & MASK == min(_signed(a), _signed(b)) & MASK
        assert alu_by_name("MAX", a, b).y & MASK == max(_signed(a), _signed(b)) & MASK
        assert alu_by_name("MINU", a, b).y == min(a, b)
        assert alu_by_name("MAXU", a, b).y == max(a, b)
        assert alu_by_name("SRA", a, b).y == (_signed(a) >> s) & MASK
        assert alu_by_name("ANDN", a, b).y == alu_by_name("AND", a, ~b & MASK).y
