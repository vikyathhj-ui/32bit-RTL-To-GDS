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

### RTL and micro-architecture (Phase 2)
*Theory only for now. Measured PPA numbers are added after Phase 4.*

**Q11. What are generate and propagate, and why does a prefix adder need them?**
- `g = a&b` (this bit makes a carry) and `p = a^b` (this bit passes a carry on).
- Groups combine with `G = G_H | P_H & G_L`, `P = P_H & P_L`. That operator is associative, so the
  carries can be computed with a tree of log₂W depth instead of a W-long chain.
- My cells: `rtl/adders/pg_black.sv` and `pg_gray.sv`.

**Q12. Why is a prefix adder log-depth?**
- Each level doubles the span a group covers (1, 2, 4, 8, 16). After log₂32 = 5 levels, every position's
  group reaches bit 0, so every carry is known.
- Ripple carry needs 32 serial steps.

**Q13. Kogge–Stone vs Brent–Kung: what's the trade-off?**
- **KS:** minimum depth (5 levels for 32 bits) and fan-out ≤ 2, but the most cells, and wires spanning
  up to 16 bit positions.
- **BK:** about half the cells and short wires, but 2·log₂W−1 = 9 levels.
- **Sklansky:** minimum depth with few cells, but fan-out up to 16.
- **Han–Carlson:** KS on odd bits plus one extra level. It sits in between.
- Which one is fastest after routing is an empirical question; Phase 4 measures it.

**Q14. What is a gray cell vs a black cell?**
- A black cell outputs G and P. A gray cell outputs only G.
- Once a group reaches bit 0, its G is the final carry and P is never needed again, so a gray cell saves
  the AND gate.

**Q15. How does your ALU share one adder across eight operations?**
- ADD uses `a + b`. SUB, SLT(U) and MIN/MAX(U) all use `a + ~b + 1`.
- SLTU is the borrow (`~cout`). SLT is `N xor V` of the difference. MIN/MAX select `a` or `b` from those.
- The same `~b` also feeds ANDN/ORN/XNOR (D-014).

**Q16. How do you implement five shift/rotate ops with one shifter?**
- A funnel right shifter: fill bits on the left (0, sign or `a`) choose SRL, SRA or ROR.
- Left ops reverse the bits, shift right, and reverse back. Reversal is wiring only.
- 5 mux stages for 0..31.

**Q17. You found a bug in your CLA before formal verification. What was it?**
- Padding inputs of a lookahead unit were tied to p = 0, which zeroed the group propagate and broke the
  carry-out (B-001).
- The fix was to pad with the operator's identity, (g = 0, p = 1).
- My exhaustive 8-bit smoke test caught it (75,701 of 151,078 vectors wrong), so the smoke test earned
  its place.

**Q18. Your adder parameter is an integer, not a string. Why?**
- Icarus Verilog (needed for cocotb) can't pass a string parameter from parent to child module. I proved
  that with a small probe.
- So `ADDER` uses named integer constants from the package, and scripts map the names. A small checker
  keeps the two tables in sync (D-012).

**Q19. Is a lint-clean design a correct design?**
- No. Lint catches structural problems (widths, unused or undriven signals, latches), not wrong
  function. I saw that Verilator doesn't even warn about a signal that is never driven and never used.
- Correctness comes from formal equivalence and simulation against the golden model (Phase 3).
