# Functional coverage

Coverage model: `tb/alu_coverage.py` (cocotb-coverage, BRIEF A3). Every result the scoreboard checks is
sampled. Per-run results are written to `results/coverage/<sim>_<ADDER>_PIPE<p>.json` (plus `.yml`
from cocotb-coverage). The roll-up is in `results/verify_summary.json`.

**Numbers in this document** are bin *definitions*: they follow from the spec and the code, not from a
run. Achieved coverage per configuration lives only in the result files above.

## Coverage points

| Point | Bins | Definition |
|---|---|---|
| `op_x_a_class` | 28 ops × 5 classes | (op, class of `a`). Ops are the 27 legal ops + ILLEGAL (codes 27–31 merged). Classes per BRIEF A3: zero, positive, negative, max (`0x7FFFFFFF`), min (`0x80000000`). "Positive"/"negative" exclude the max/min values. |
| `op_x_b_class` | 20 binary ops × 5 classes | (op, class of `b`), binary ops + ILLEGAL. Unary ops are excluded (see below). |
| `op_x_flag` | 28 ops × 4 flags × 2 values, minus unreachable | (op, flag, value) for N, Z, C, V. |
| `shift_amount` | 5 ops × 5 bins | SLL/SRL/SRA/ROL/ROR × shift amount `b[4:0]` ∈ {0, 1, 2–15, 16–30, 31}. |
| `clz_result` | 33 | CLZ result 0..32 (32 = zero input). |
| `ctz_result` | 33 | CTZ result 0..32. |

Total defined bins: 495. The JSON reports bins, covered, percent and missed bins per point.

## Bins left out, and why they are unreachable

Left-out bins are listed with their reason in each coverage JSON (`points.<name>.ignored`). They fall
into four classes:

| Bins | Count | Reason |
|---|---|---|
| `op_x_b_class` for CLZ, CTZ, CPOP, SEXT.B, SEXT.H, ZEXT.H, REV8, ORC.B | 8 ops | Unary ops ignore `b` (SPEC section 3), so `b`'s class has no meaning for them. `b`-independence is still checked: the scoreboard compares every result for random `b`, and formal equivalence covers all `b`. |
| `op_x_flag` C=1 and V=1 for every op except ADD, SUB | 52 (26 ops × 2) | SPEC section 4: C = V = 0 for all other ops, including SLT/SLTU/MIN/MAX, which use the adder internally. |
| `op_x_flag` N=1 for SLT, SLTU, CLZ, CTZ, CPOP, ZEXT.H, ILLEGAL | 7 | Bit 31 of the result is always 0. SLT/SLTU give 0/1; the counts are ≤ 32; ZEXT.H clears the top 16 bits; illegal gives `y = 0`. |
| `op_x_flag` Z=0 for ILLEGAL | 1 | SPEC section 5: illegal opcodes give `y = 0`, so Z is always 1. |

**Why "unreachable" is a proven claim, not an assumption:**
- Formal equivalence (`formal/alu_equiv.sv`, all ADDER × PIPE) proves that the DUT's `y` and `flags`
  equal the behavioural reference for **every** input.
- The reference produces none of these values by construction.
- So the DUT cannot reach any left-out bin, and none of them hides a hole in the stimulus.

## Stimulus that targets the hard bins
- **CLZ/CTZ 0..32:** the directed test drives every single-bit word, every low-ones mask `(1<<k)-1` and
  every high-ones mask. The random generator has a "long zero run at either end" operand class
  (`tb/alu_tb.py` `rand_operand`).
- **ORN with Z=1** (needs `a = 0`, `b = 0xFFFFFFFF`): directed vector, plus the corner classes in random.
- **Shift amounts:** `b` is biased toward 0/1/31 with random upper bits, so the use of only `b[4:0]` is
  exercised.
