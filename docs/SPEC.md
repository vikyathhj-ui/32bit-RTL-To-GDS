# ALU functional specification

Source of truth: `docs/BRIEF.md` Part A (binding). This document makes Part A precise. Where Part A was
ambiguous, the clarification agreed with the project owner is marked **[clarified]** with its DECISIONS
entry.

The golden model `model/alu_ref.py` implements exactly this document.

## 1. Interface

Top module: `alu_top` (`rtl/alu_top.sv`, Phase 2).

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock. All registers are rising-edge. |
| `rst_n` | in | 1 | Active-low reset. Asynchronous assert, synchronous de-assert (D-010). |
| `in_valid` | in | 1 | `op`, `a` and `b` are valid this cycle. |
| `op` | in | 5 | Opcode (section 3). |
| `a` | in | 32 | Operand 1 (rs1). |
| `b` | in | 32 | Operand 2 (rs2). Ignored by unary ops; only `b[4:0]` is used by shifts and rotates. |
| `out_valid` | out | 1 | `y`, `flags` and `illegal_op` hold the result of one accepted operation. |
| `y` | out | 32 | Result. |
| `flags` | out | 4 | `{N, Z, C, V}` = `flags[3:0]` (section 4). |
| `illegal_op` | out | 1 | The operation had an undefined opcode (section 5). |

No back-pressure: the ALU accepts one operation per cycle, every cycle.

### Parameters

| Parameter | Values | Default | Meaning |
|---|---|---|---|
| `ADDER` | `RCA`, `CLA4`, `CSLA`, `BK`, `KS`, `SK`, `HC`, `BEH` | `BEH` | Adder core architecture (BRIEF A2 table). Every value must give identical function. |
| `PIPE` | 0, 1 | 0 | 1 adds a register after the adder/shifter stage. |

## 2. Timing and reset

**[clarified, D-006]** Inputs **and** outputs are registered, so static timing analysis sees
register-to-register paths (BRIEF A2). Part A's "1-cycle latency" counts the single compute stage
between the two register banks. Measured at the ports, latency is defined as follows.

> **Latency L** = the number of rising clock edges from the edge that samples `in_valid=1` (inclusive)
> to the edge after which `out_valid=1` for that operation (inclusive).
> **L = 2** for `PIPE=0` and **L = 3** for `PIPE=1`.

- **Throughput:** one operation per cycle. Results come out in issue order. `out_valid` at cycle
  *t + L* equals `in_valid` at cycle *t* (after reset).
- **Reset:** while `rst_n=0`, and in the first cycle after release, `out_valid=0`. Reset clears only
  the valid pipeline. Data registers are not reset.
- **Hold (D-010):** data registers load only when the valid bit of their stage is 1, so `y`, `flags`
  and `illegal_op` keep their last value while `out_valid=0`.
  - **Contract:** these outputs are meaningful **only when `out_valid=1`**.
  - Holding is a power optimisation, not a guarantee consumers may rely on.

### Timing diagrams (WaveDrom)

The same issue sequence is used in both diagrams: ADD(5, 7), AND(0xF0F0, 0xFF00), an illegal opcode 27,
then a bubble.

PIPE=0 (L = 2):
```wavedrom
{ "signal": [
  { "name": "clk",        "wave": "p.......", "node": ".a.b...." },
  { "name": "in_valid",   "wave": "01..0..." },
  { "name": "op",         "wave": "x345x...", "data": ["ADD", "AND", "27"] },
  { "name": "a",          "wave": "x345x...", "data": ["5", "0xF0F0", "0x1234"] },
  { "name": "b",          "wave": "x345x...", "data": ["7", "0xFF00", "0x5678"] },
  {},
  { "name": "out_valid",  "wave": "0..1..0." },
  { "name": "y",          "wave": "x..345..", "data": ["12", "0xF000", "0"] },
  { "name": "flags NZCV", "wave": "x..3.4..", "data": ["0000", "0100"] },
  { "name": "illegal_op", "wave": "x..0.1.." }
 ],
  "edge": ["a~>b L=2"],
  "head": { "text": "PIPE=0: ADD sampled at edge 1, result valid after edge 2" } }
```

PIPE=1 (L = 3):
```wavedrom
{ "signal": [
  { "name": "clk",        "wave": "p........", "node": ".a..b...." },
  { "name": "in_valid",   "wave": "01..0...." },
  { "name": "op",         "wave": "x345x....", "data": ["ADD", "AND", "27"] },
  { "name": "a",          "wave": "x345x....", "data": ["5", "0xF0F0", "0x1234"] },
  { "name": "b",          "wave": "x345x....", "data": ["7", "0xFF00", "0x5678"] },
  {},
  { "name": "out_valid",  "wave": "0...1..0." },
  { "name": "y",          "wave": "x...345..", "data": ["12", "0xF000", "0"] },
  { "name": "flags NZCV", "wave": "x...3.4..", "data": ["0000", "0100"] },
  { "name": "illegal_op", "wave": "x...0.1.." }
 ],
  "edge": ["a~>b L=3"],
  "head": { "text": "PIPE=1: one extra register after the adder/shifter stage" } }
```

The diagram's `y` and `flags` values for ADD, AND and the illegal op are the outputs of
`model/alu_ref.py` (e.g. `python3 model/alu_ref.py AND 0xF0F0 0xFF00`). After the last result, the
outputs hold (D-010).

## 3. Opcode table (D-009)

There are 27 operations on a 5-bit opcode. Codes 27–31 are illegal.

**Notation:**
- `a` and `b` are 32-bit unsigned bit vectors, and `s = b[4:0]`.
- `signed(x)` is the two's-complement value of `x`.
- `x[i]` is bit `i`, and `{}` is concatenation.
- All results are truncated to 32 bits.

**Spec references:**
- [RV32I] = RISC-V unprivileged ISA manual, RV32I integer register-register operations.
- `zb#…` = `riscv-isa-manual/src/unpriv/zb.adoc`, instruction anchor (e.g. `zb#insns-clz`), checked at
  commit `8fb3965fe4b5`.

| Code | Op | Unit | Definition (bit-exact) | Ref |
|---:|---|---|---|---|
| 0 | ADD | adder | `y = a + b` | RV32I |
| 1 | SUB | adder | `y = a + ~b + 1` (= `a − b`) | RV32I |
| 2 | SLL | shifter | `y = a << s` (zeros shifted in) | RV32I |
| 3 | SLT | adder | `y = (signed(a) < signed(b)) ? 1 : 0` | RV32I |
| 4 | SLTU | adder | `y = (a < b unsigned) ? 1 : 0` | RV32I |
| 5 | XOR | logic | `y = a ^ b` | RV32I |
| 6 | SRL | shifter | `y = a >> s` (zeros shifted in) | RV32I |
| 7 | SRA | shifter | `y = signed(a) >> s` (copies of `a[31]` shifted in) | RV32I |
| 8 | OR | logic | `y = a \| b` | RV32I |
| 9 | AND | logic | `y = a & b` | RV32I |
| 10 | MIN | adder | `y = (signed(a) < signed(b)) ? a : b` | zb#insns-min |
| 11 | MAX | adder | `y = (signed(a) < signed(b)) ? b : a` | zb#insns-max |
| 12 | MINU | adder | `y = (a < b unsigned) ? a : b` | zb#insns-minu |
| 13 | MAXU | adder | `y = (a < b unsigned) ? b : a` | zb#insns-maxu |
| 14 | ANDN | logic | `y = a & ~b` | zb#insns-andn |
| 15 | ORN | logic | `y = a \| ~b` | zb#insns-orn |
| 16 | XNOR | logic | `y = ~(a ^ b)` | zb#insns-xnor |
| 17 | ROL | shifter | `y = (a << s) \| (a >> (32 − s))`; for `s = 0`, `y = a` | zb#insns-rol |
| 18 | ROR | shifter | `y = (a >> s) \| (a << (32 − s))`; for `s = 0`, `y = a` | zb#insns-ror |
| 19 | CLZ | count | `y` = number of 0 bits above the highest 1 bit, scanning from bit 31; **32 if `a = 0`** | zb#insns-clz |
| 20 | CTZ | count | `y` = number of 0 bits below the lowest 1 bit, scanning from bit 0; **32 if `a = 0`** | zb#insns-ctz |
| 21 | CPOP | count | `y` = number of 1 bits in `a` (0..32) | zb#insns-cpop |
| 22 | SEXT.B | byte | `y = {{24{a[7]}}, a[7:0]}` | zb#insns-sext_b |
| 23 | SEXT.H | byte | `y = {{16{a[15]}}, a[15:0]}` | zb#insns-sext_h |
| 24 | ZEXT.H | byte | `y = {16'b0, a[15:0]}` | zb#insns-zext_h |
| 25 | REV8 | byte | `y = {a[7:0], a[15:8], a[23:16], a[31:24]}` | zb#insns-rev8 |
| 26 | ORC.B | byte | for each byte *k* in 0..3: `y[8k+7:8k] = (a[8k+7:8k] != 0) ? 8'hFF : 8'h00` | zb#insns-orc_b |
| 27–31 | — | — | illegal: `y = 0`, `illegal_op = 1` | section 5 |

- **Unary ops** (CLZ, CTZ, CPOP, SEXT.B, SEXT.H, ZEXT.H, REV8, ORC.B) ignore `b` entirely.
- **ROL/ROR at `s = 0`:** the shift by 32 in the Zbb pseudo-code gives 0 under its semantics, so the
  result is `a`.
- **Units:** the "Unit" column says which shared hardware block produces the result (section 6).

## 4. Flags (D-008)

`flags = {N, Z, C, V}`. They are produced in the same cycle as `y` and are valid with `out_valid`.

| Op | N | Z | C | V |
|---|---|---|---|---|
| ADD | `y[31]` | `y == 0` | carry-out of `a + b` (bit 32) | signed overflow: `a[31] == b[31] && y[31] != a[31]` |
| SUB | `y[31]` | `y == 0` | **carry-out of `a + ~b + 1`**, i.e. **1 = no borrow (a ≥ b unsigned)** **[clarified, D-008]** | signed overflow: `a[31] != b[31] && y[31] != a[31]` |
| all other legal ops | `y[31]` | `y == 0` | 0 | 0 |
| illegal opcode | 0 | 1 | 0 | 0 |

- **Ops that use the adder internally** (SLT, SLTU, MIN, MAX, MINU, MAXU) still report C = V = 0. Their
  architectural result is the comparison or selection, not the difference.
- **Why "no borrow":** it is the adder's raw carry-out when subtracting as `a + ~b + 1`, so no extra
  inverter is needed (ARM/6502 convention). x86 uses the inverted ("borrow") sense.

## 5. Illegal opcodes

For `op ∈ {27, 28, 29, 30, 31}` with `in_valid = 1`:
- `y = 0`, `flags = 4'b0100` (Z=1);
- `illegal_op = 1`;
- `out_valid` behaves as for any other operation.

For legal opcodes, `illegal_op = 0`. No other side effects.

## 6. Micro-architecture rules (copied from BRIEF A2 for traceability)

- One shared adder serves ADD, SUB, SLT, SLTU, MIN, MAX, MINU and MAXU (comparison by subtraction).
- One shared logarithmic barrel shifter serves SLL, SRL, SRA, ROL and ROR (left shift via bit reversal).
- CLZ uses a log-depth leading-zero tree; CTZ is a bit reversal followed by the CLZ tree.
- CPOP uses a compressor/adder tree.
- The adder core is selected by `ADDER`. Prefix adders (BK, KS, SK, HC) use explicit generate/propagate
  cells built with `generate` loops.

Design detail (block diagram, depth/fan-out per adder) goes in `docs/MICROARCH.md` (Phase 5).

## 7. Verification requirements (BRIEF A3) and where they are implemented

| Requirement | Implemented in | Phase |
|---|---|---|
| Golden model, bit-exact, independent of RTL | `model/alu_ref.py` | 1 ✅ |
| Model checked against hand vectors and the spec | `model/test_alu_ref.py` | 1 ✅ |
| Model checked against the RISC-V reference simulator | `model/spike_xcheck.py` → `results/model_xcheck.json` | 1 ✅ |
| Directed corners (0, 1, −1, INT_MIN, INT_MAX, alternating bits, shift amounts 0/1/31, op × flag edges) | `tb/` (cocotb) | 3 |
| ≥10⁶ constrained-random vectors per adder config (Verilator) | `tb/` | 3 |
| Functional coverage: op × operand class, flags per op, shift bins, CLZ/CTZ 0..32 | `tb/` (cocotb-coverage) | 3 |
| Formal: per-adder miter `adder(a,b,cin) == a+b+cin` | `formal/` | 3 |
| Formal: full ALU vs behavioural reference ALU | `formal/` | 3 |
| Formal: `out_valid` latency = L | `formal/` | 3 |
| Lint: `verilator --lint-only -Wall` clean | `Makefile` | 2 |

**Note on the Zbb test vectors [clarified, D-007]:** the ratified Zbb chapter contains no numeric
examples. Instead, the model is tested against:
- vectors hand-derived from each instruction's ratified Operation block;
- the `strlen`/`strcmp` idioms from `bitmanip-examples.adoc`;
- Spike, the RISC-V reference simulator, on every legal op.
