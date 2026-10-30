# Learning notes

Concepts you must understand to own this project. Each one is explained simply, with pointers into
the code. Filled in phase by phase.

## Phase 0
- **Why the old ALU was wrong** (`docs/AUDIT.md`). The output mux used the opcode from the *current*
  cycle to pick a result computed in the *previous* cycle. **Rule:** every control signal must travel
  down the pipeline together with the data it controls.
- **Non-blocking assignment (`<=`) reads old values.** `zero <= (result == 0)` in the same clocked block
  as `result <= ...` sees last cycle's `result`. Compute flags from the same expression that feeds `y`.
- **Ripple carry vs. lookahead.** A loop `C[i] = G[i-1] | P[i-1] & C[i-1]` is a chain of 32 dependent
  stages, so its delay grows as O(n). Lookahead/prefix adders compute carries in parallel trees with
  O(log n) depth. Phase 2 implements both.

## Phase 1 — spec and golden model

### Two's complement, and why one adder does ADD and SUB
- A 32-bit pattern can be read as unsigned (0 … 2³²−1) or signed (−2³¹ … 2³¹−1). The bits don't
  change; only the interpretation does.
- **Negation:** `−b = ~b + 1`. So `a − b = a + ~b + 1`. Subtraction is the same adder with `b` inverted
  and carry-in = 1. See `model/alu_ref.py` `alu()` → `SUB` and `add_with_flags()`.

### Carry vs overflow: two different questions
- **C (carry)** answers "did the *unsigned* result wrap?", i.e. bit 32 of the sum.
  - Example: `0xFFFFFFFF + 1 = 0` with C=1.
- **V (overflow)** answers "is the *signed* result wrong?". It happens when both operands have the same
  sign and the result's sign differs.
  - Example: `0x7FFFFFFF + 1 = 0x80000000` (INT_MAX + 1 became negative), so V=1 and C=0.
- **Both at once:** `0x80000000 + 0x80000000 = 0` with C=1 and V=1. Tests:
  `model/test_alu_ref.py::FLAG_VECTORS`.

### Why SUB's C means "no borrow" (D-008)
- `a + ~b + 1` produces a carry-out exactly when `a ≥ b` (unsigned). So the raw carry-out means "no
  borrow".
- ARM uses this sense; x86 inverts it.
- We keep the raw carry, so no extra gate is needed. Property test: `sub.c == int(a >= b)`.

### Compare by subtraction (SLT, SLTU, MIN, MAX)
- **SLTU:** `a < b` unsigned ⇔ `a − b` borrows ⇔ C = 0.
- **SLT:** `a < b` signed ⇔ N ≠ V on the subtraction. The sign of the difference is wrong exactly when
  it overflowed.
- So one adder plus a couple of gates gives all four comparisons and MIN/MAX. That is the
  resource-sharing rule in SPEC section 6. (The RTL in Phase 2 implements it; the model just uses Python
  comparisons, on purpose, so the two are independent: D-011.)

### What each Zbb op is for (real software use)

| Op | Software use |
|---|---|
| ANDN / ORN / XNOR | Bit masking without a separate NOT (`x & ~mask`). |
| CLZ | Normalising floating point, finding the highest set bit (log2), priority encoders. |
| CTZ | Finding the lowest set bit, iterating over set bits; `strlen` uses it on the `orc.b` result. |
| CPOP | Population count: Hamming distance, bitsets, error counting. |
| MIN / MAX (U) | Clamping without branches. |
| SEXT.B / SEXT.H / ZEXT.H | Replace 2-instruction shift idioms when loading bytes or halves. |
| ROL / ROR | Hash functions and cryptography (SHA-2, ChaCha) rotate constantly. |
| REV8 | Endianness swaps (network byte order); `strcmp` uses it to compare words in byte order. |
| ORC.B | Find a zero byte in a word: the core of fast `strlen`/`strcpy`. |

### Why a golden model, and why check it against Spike
- **The model is the "answer key"** for millions of random RTL tests in Phase 3. If the model is wrong,
  the RTL will be "fixed" to match a wrong answer.
- **Hand vectors** catch misunderstandings of the spec, but a person writes both the model and the test.
- **Spike** is the official RISC-V reference simulator, written by other people. Agreement on every op is
  strong evidence that the model matches the ISA. Result: `results/model_xcheck.json`.
- **Mutation check:** a check that never fails proves nothing. Breaking the model on purpose (D-007) and
  seeing the check fail proves that it really compares.

## Phase 2 — RTL

### Generate and propagate: the idea behind every fast adder
- **Per-bit signals:** `g = a & b` means "this bit **generates** a carry by itself". `p = a ^ b` means
  "this bit **propagates** an incoming carry".
- **Groups:** a group of bits [i..j] also has a (G, P). For a high part H and a low part L:
  `G = G_H | P_H & G_L` and `P = P_H & P_L`. That is the **prefix operator** ("dot", `o`). It's
  `pg_black` in `rtl/adders/pg_black.sv`.
- **Why it matters:** the operator is **associative**, so groups can be combined in any tree shape. The
  tree shape *is* the adder architecture.
- **Gray cells:** once a group reaches bit 0, its G **is** the carry, and P is no longer needed. That is
  the gray cell (`pg_gray.sv`).
- **Carry-in:** `cin` is folded into bit 0 (`g0 = a0&b0 | p0&cin`), so "group reaches bit 0" includes
  the carry-in. Sum bit `i` = `p_i ^ carry_into_i`.

### The four prefix trees on 8 bits (● black/gray cell, | wire)
```
Kogge-Stone (3 levels, 17 cells, fan-out <= 2, long wires)
  bit: 7 6 5 4 3 2 1 0
  L0 : ● ● ● ● ● ● ● |     span 1: every bit i>=1 joins i-1
  L1 : ● ● ● ● ● ● | |     span 2
  L2 : ● ● ● ● | | | |     span 4
Sklansky (3 levels, 12 cells, fan-out grows: bit 3 drives 4 cells at L2)
  L0 : ● | ● | ● | ● |     bits with bit0 set (odd bits) join bit i-1
  L1 : ● ● | | ● ● | |     bits with bit1 set join the top of the lower half
  L2 : ● ● ● ● | | | |     bits 4..7 all join bit 3
Brent-Kung (5 levels = 2*log2(8)-1, 11 cells, fan-out <= 2, short wires)
  up : ● | ● | ● | ● |  → ● | | | ● | | |  → ● | | | | | | |
  down:  | | ● | | | | |  → | ● | ● | ● | |   (fills in 5, then 2,4,6)
Han-Carlson (4 levels, KS on odd bits only, then one fix-up level for even bits)
```
| Architecture | Depth | Cells | Wiring |
|---|---|---|---|
| Kogge-Stone (`adder_ks.sv`) | minimum (log₂W) | the most | wiring-heavy |
| Sklansky (`adder_sk.sv`) | minimum (log₂W) | few | high fan-out |
| Brent-Kung (`adder_bk.sv`) | almost double | the fewest | short wires |
| Han-Carlson (`adder_hc.sv`) | one level more than KS | about half of KS | in between |

**Exam question:** which one wins after place-and-route? That depends on wires and fan-out, not just
depth. Phase 4 measures it.

### CLA and carry-select (the "classic" fast adders)
- **CLA4** (`adder_cla4.sv`):
  - A 4-bit lookahead unit computes 3 carries in parallel from (g, p, cin) and outputs a group (G, P).
  - Stacking units into a tree (8 → 2 → 1 for 32 bits) gives log₄ depth.
  - The tree is a prefix structure too, with radix 4.
- **Carry-select** (`adder_csla.sv`):
  - Each 8-bit block computes its sum twice, for carry-in 0 and 1.
  - The real carry then only passes through one mux per block.
  - It spends area (two adders per block) to buy speed.

### Identity elements (lesson from bug B-001)
- **What went wrong:** when padding a 4-input lookahead unit that has only 2 real inputs, the padding
  must not change the answer. Padding with p = 0 forced the group propagate (`&p`) to 0 and broke
  `cout`.
- **The fix:** pad with the identity of the operator, (g = 0, p = 1).
- **General rule:** this applies to any reduction. Pad an AND with 1, an OR with 0, a sum with 0.

### Funnel shifter (`rtl/shifter.sv`)
- **Concept:** put fill bits on the left of `a` and shift the 63-bit concatenation right. The fill bits
  choose the operation:
  - zeros: logical shift;
  - sign copies: arithmetic shift;
  - `a` itself: rotate.
- **Log stages:** 5 stages of 2:1 muxes (shift by 16, 8, 4, 2, 1). Any amount 0..31 is a combination of
  these, so depth is log₂32 = 5 muxes, not 31.
- **Left shifts:** reverse the bits, shift right, reverse back. Reversal is free; it's just wires.

### Leading-zero count tree (`rtl/clz_tree.sv`)
- **Concept:** split the word in half. If the top half has a 1, the answer is the top half's count;
  otherwise it is 16 plus the bottom half's count. Recurse.
- **Depth:** each level is one mux, so depth is log₂32 = 5.
- **CTZ:** the same tree on the bit-reversed word.

### Lint vs synthesis vs verification
- **`make lint`** (Verilator `-Wall`) catches *style and structure* problems: unused or undriven
  signals, width mismatches, latches.
  - It does **not** prove the design computes the right thing.
  - Seen in this project: a signal that is never driven *and* never used produces no warning at all.
- **`make synth-check`** proves Yosys can build it with no latches or multiple drivers. It also doesn't
  prove function.
- **Function** is proven in Phase 3: formal equivalence plus cocotb against the golden model. The only
  functional check in Phase 2 is the adder smoke test.

## Phase 3 — verification

### Scoreboard testbench (`tb/alu_tb.py`)
- **Driver:** puts one operation on the inputs per cycle, sometimes with a bubble (`in_valid=0`).
- **Scoreboard:** a queue. Each issued operation pushes its *expected* result, taken from the golden
  model.
- **Monitor:** every time `out_valid=1`, pops the queue and compares `y`, `flags` and `illegal_op`. It
  also checks the result arrived exactly L cycles after issue, so it tests timing, not just order.
- **Why drive and sample on the falling edge:** values read there are the settled result of the previous
  rising edge, which avoids race conditions between the testbench and the design.

### Constrained random
- **The problem with pure random:** 32-bit operands almost never hit the interesting values (0, −1,
  INT_MIN, single bits, long zero runs for CLZ).
- **"Constrained" means a weighted mix:** mostly random, with corners injected on purpose. See
  `rand_operand()`.
- **Seeds:** the seed is recorded, so any failure can be replayed exactly.

### Functional coverage (`tb/alu_coverage.py`, `docs/COVERAGE.md`)
- **What it answers:** "did my stimulus actually exercise X?" For example: every op with a negative
  operand, every CLZ result 0..32, every flag value each op can produce.
- **It measures the test, not the design.** 100% coverage with a broken scoreboard would still pass
  bugs.
- **Unreachable bins** are left out with a written reason. Formal equivalence then proves they really
  are unreachable.

### How a formal miter works (`formal/adder_miter.sv`)
1. Feed the same inputs to two circuits: the adder under test, and the obviously-correct `a + b + cin`.
2. Assert that their outputs are equal.
3. The solver tries to find *any* input that breaks the assertion.
   - If none exists, the two are equal for all 2⁶⁵ inputs. That is a proof, not a sample.
   - If one exists, you get the exact counterexample as a waveform.
- **Evidence it works:** breaking one prefix index in KS made the miter fail immediately with a trace.

### k-induction (how SBY proves sequential properties, `formal/alu_equiv.sv`)
- **Base case:** from reset, the property holds for the first k cycles (a bounded check).
- **Induction step:** if the property held for any k consecutive cycles, it holds in cycle k+1, starting
  from *any* state, even unreachable ones.
- **Why k must be at least the pipeline depth:** a "garbage" start state gets flushed out of the
  pipeline within L cycles. Any garbage that would reach the output shows up inside the k-cycle window
  and is ruled out by the assumption.

### Coverage vs formal: why do both?
- **Formal** proves the RTL equals the reference for every input, but only for the properties you wrote,
  only within the formal model, and only against a reference *you* wrote.
- **Simulation against the golden model** is an independent second reference (Python, checked against
  Spike). It also exercises the real testbench interface, reset sequencing and simulators.
- **Coverage** shows the simulation didn't just repeat easy cases.
- Together: two independent references agreeing, plus evidence the stimulus was meaningful.

### Tools are not always right (D-021)
- **What happened:** Icarus evaluated comparisons inside port connections wrongly in one module, while
  Verilator and formal agreed the RTL was correct.
- **The lesson:** when two tools disagree, isolate with minimal cases before "fixing" the design. Then
  choose a coding style that every tool evaluates the same way.

## Phase 4+
(to be added)
