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

## Phase 2+
(to be added)
