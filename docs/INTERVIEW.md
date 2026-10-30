# Interview preparation

30+ likely questions, answered using **this project's actual numbers**. Every number is taken from
`results/summary.json`. Filled in from Phase 3 onwards, once real results exist.

Required topics (docs/BRIEF.md Phase 5): why prefix adders are log-depth; KS vs BK fan-out and wiring;
why post-route changes the ranking; setup vs hold and why hold matters at the FF corner; what ABC did;
how the formal miter works; coverage vs formal; energy/op vs power.

## Questions

### Specification and golden model (Phase 1)

**Q1. Your ALU has N, Z, C and V flags. What is the difference between C and V?**
- C is unsigned wrap-around (the carry out of bit 31). V is signed overflow (same-sign operands, but the
  result has the other sign).
- Example from the tests: `0x7FFFFFFF + 1` gives V=1 and C=0; `0xFFFFFFFF + 1` gives C=1 and V=0.
- Source: `docs/SPEC.md` section 4, `model/test_alu_ref.py::FLAG_VECTORS`.

**Q2. What does C mean after a subtraction in your design, and why?**
- C=1 means "no borrow" (a ≥ b unsigned). It is the raw carry-out of `a + ~b + 1`, so it costs no extra
  logic. That is the ARM convention; x86 inverts it.
- I chose it deliberately and documented it, because a later SoC project (P6) reuses this ALU. See D-008.

**Q3. RISC-V has no flags. Why does your ALU have them?**
- The brief asks for them, and they make the ALU reusable in non-RISC-V datapaths.
- They are defined only for ADD/SUB; for every other op, C = V = 0. Even SLT and MIN/MAX, which use the
  adder internally, report C = V = 0, because their architectural result is a comparison.

**Q4. How do you compute SLT and SLTU with one adder?**
- Compute `a − b`. SLTU is the borrow (C = 0). SLT is `N xor V`: the sign of the difference, corrected
  for overflow.
- MIN/MAX(U) then just select `a` or `b` from that bit.

**Q5. Why did you write a separate golden model instead of trusting the RTL?**
- Random tests need an independent answer key. If the reference shares code or structure with the RTL,
  their bugs line up and the tests pass anyway.
- My model is written from the ratified spec text, in simple scan or loop form, before any RTL existed
  (D-011).

**Q6. How do you know your golden model is right?**
Three layers:
1. Hand-computed vectors and algebraic properties: `results/model_test.txt` (162 tests pass).
2. The `strlen`/`strcmp` idioms from the Zbb spec's own examples.
3. A cross-check against Spike, the official RISC-V simulator: `results/model_xcheck.json` (8,572
   vectors across all 27 ops, 0 mismatches).

I also broke the model on purpose and confirmed that the check fails. A check that can't fail proves
nothing.

**Q7. The brief said "test against the Zbb spec examples". What did you do when you found it had none?**
- I stopped and raised it instead of quietly downgrading. I proposed the closest honest alternative
  (spec-derived vectors plus Spike), and it was approved (D-007). The same happened for the latency
  definition (D-006).
- In industry that's the difference between a spec clarification and a silent spec deviation.

**Q8. What is the latency of your ALU and how is it defined?**
- Inputs and outputs are registered, so `out_valid` follows `in_valid` by 2 clock edges (3 with
  `PIPE=1`), at one operation per cycle.
- The definition is in `docs/SPEC.md` section 2. Phase 3 proves it formally.

**Q9. Why register both the inputs and the outputs?**
- So that static timing analysis sees pure register-to-register paths. The adder comparison then isn't
  distorted by assumed input or output delays.
- The cost is one extra cycle of latency.

**Q10. Why does CLZ of zero return 32?**
- The Zbb spec defines CLZ as `(XLEN−1) − HighestSetBit`, and HighestSetBit returns −1 for 0. So the
  result is XLEN = 32. CTZ of 0 is also 32.
- This matters for the coverage plan: CLZ/CTZ results run over 0..32, which is 33 bins, not 32.

(Phase 2+ questions to be added: prefix adders, KS vs BK, ABC, the formal miter, coverage vs formal,
setup/hold, post-route ranking, energy/op.)
