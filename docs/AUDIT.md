# Audit of the legacy design (Phase 0)

Scope: the state of `main` at commit `907befc` (`src/alu32_final.v`, `config.json`), now moved to
`legacy/`, plus the separate `vikyathhj-ui/STA` repository that this project absorbs.

Evidence:

- **Code reading.** Line numbers refer to `legacy/alu32_final.v`.
- **A probe simulation.** `legacy/tb_probe.v`, run by `scripts/legacy_probe.sh` (Icarus Verilog). Its log is
  `results/legacy_probe.txt`. Lines quoted below come from that log.

The probe holds each opcode stable for 3 cycles before sampling, which is the most favourable case for
this design. The exceptions are the back-to-back test and the `valid_out` test.

## A. Functional bugs (confirmed by simulation)

### A1. Opcode decode: clock-gate enables disagree with the result mux
- **Code:** enables at lines 80–84 group opcodes as logic 2–7, shift 8–12, compare 13–19 and special
  ≥16. The result `case` at lines 223–260 puts XNOR at 8 (line 236), the shifts at 9–13 and ROR at 13
  (line 242).
- **Effect:**
  - **XNOR (8)** reads `l_xnor`, but opcode 8 enables the *shift* stage. `l_xnor` is never written.
  - **ROR (13)** reads `sh_ror`, but opcode 13 enables the *compare* stage. `sh_ror` keeps whatever the
    last shift op left in it.
  - Compare (13–19) and special (≥16) enables also overlap at 16–19.
- **Probe log:**
  ```
  XNOR   op= 8 A=f0f0f0f0 B=ff00ff00 -> y=xxxxxxxx exp=f00ff00f FAIL
  ROR1   op=13 A=00000003 B=00000001 -> y=c0000000 exp=80000001 FAIL
  ```
  `c0000000` is ROR(0x80000001, 1), the operands of the *previous* (ROL) test.

### A2. Result mux selects with the live opcode, not the registered one
- **Code:** stage-1 registers capture data at edge *t*. At edge *t+1*, the output stage selects with
  `case (opcode)` (line 223), which is the opcode presented *in cycle t+1*. The registered copies
  (`s_opcode`, `l_opcode`, …) are written but never used.
- **Effect:** the design only works if the opcode is held for at least two cycles. Back-to-back
  different ops return the wrong result, so a pipelined datapath cannot use it.
- **Probe log:**
  ```
  b2b: after ADD(10,20) issued, cycle+1 y=xxxxxxxx (exp 0000001e)
  ```

### A3. Z and N flags are one cycle stale
- **Code:** lines 263–264 compute `zero <= (result == 0)` and `negative <= result[31]` in the same
  clocked block that assigns `result`. A non-blocking read sees the *old* `result`.
- **Probe log:**
  ```
  y=00000001 z=1 (z should be 0 when y!=0)
  ```

### A4. `valid_out` gets stuck high
- **Code:** each stage's `*_valid` register (e.g. `s_valid`, lines 109–113) is only clocked when that
  stage's gated clock is enabled, and that only happens when `valid_in=1`. Once set to 1, it is never
  cleared except by reset. `valid_out` (line 220) is the OR of these registers.
- **Probe log:**
  ```
  valid_in=0 for 4 cycles -> valid_out=1 (exp 0)
  ```

## B. Claims that don't match the code

### B1. "Carry-lookahead adder" is a ripple-carry adder
`cla_add` (lines 19–33) computes `C[i] = G[i-1] | (P[i-1] & C[i-1])` in a loop (line 29). That is a
serial carry chain 32 stages deep: ripple carry, not lookahead. It also uses `P = X | Y` (line 26).
OR is a valid "carry-transmit" signal for the carry chain, but it is not the XOR propagate that sum and
prefix formulations use.

Synthesis (ABC) may still restructure the chain into something faster. However, the RTL does not
describe a CLA, and the original flow produced no report showing what was built.

### B2. "29 operations"
The `case` statement does define 29 opcodes (`5'b00000`–`5'b11100`), so the count itself matches.
However:
- 2 of them (XNOR, ROR) never produce correct results (A1);
- all of them fail when issued back-to-back (A2);
- several are not RISC-V operations (SGT, SGTU, EQ, NEQ, ABS, NOT, NAND, NOR, SWAP, PASS_A, PASS_B,
  BREV).

The new design implements the 27 RV32I + Zbb ops defined in `docs/BRIEF.md`.

### B3. Resume numbers cannot be reproduced
The resume quotes **3,437 cells, 22,347 µm², 4.98 mW, and −6.62 ns WNS at the SS corner**.

- No LibreLane/OpenLane run directory, report, log or metrics file is committed; `.gitignore` excludes
  `runs/` and `*.log`.
- There is no script that produces these values.
- None of them can be traced to a source, so none will be reused. All new numbers will come from
  `results/summary.json`.
- A WNS of −6.62 ns at the configured 15 ns clock (`legacy/config.json`) would itself mean the design
  **failed** setup timing at SS by 6.62 ns.

### B4. No verification
The repository has no testbench, no reference model and no formal checks. `legacy/tb_probe.v` was written
during this audit only to confirm the bugs above.

## C. Design-quality issues (not functional failures, but would not pass review)

1. **Hand-built latch clock gating** (lines 87–98: `always @(clk or en) if (!clk) cg <= en;` then
   `clk & cg`).
   - The latch + AND structure is the textbook ICG, but here it is built from generic logic instead of
     the library's integrated clock-gate cell (`sky130_fd_sc_hd__dlclkp`).
   - Synthesis infers latches in the clock path.
   - CTS and STA must then handle clock gating checks on generic gates, and five derived clocks
     complicate timing for no measured benefit.
2. **No resource sharing.**
   - ADD and SUB use two full adders (lines 114–115).
   - SLT, SGT, SLTU, SGTU, MAX and MIN each have their own magnitude comparator (lines 175–202).
   - Five shift/rotate results are each computed separately.
3. **Mixed reset style.** Asynchronous active-high `rst`. The data registers in stage 1 are never reset
   (only the `*_valid` ones are). `y` is reset to 0, but each stage's result stays X until that stage
   is used for the first time, which is the source of the `xxxxxxxx` outputs in A1 and A2.
4. **Clock gating and the output stage use different clocks** (gated vs. ungated). This creates
   cross-"clock" paths that the SDC does not describe.
5. **`legacy/config.json`** sets `FP_CORE_UTIL` 40 and `PL_TARGET_DENSITY_PCT` 45 at a 15 ns period, with
   no project SDC. The flow's default constraints were used, and those don't model the gated clocks,
   so any timing number from it says little about the gated paths.

## D. Checked and found correct (not bugs)

- **ROL/ROR by 0** (lines 158–159, `A >> (32-B[4:0])`). In Verilog, a shift by ≥ the operand width gives
  0, so ROL by 0 returns `A`. The probe confirms `ROL0 ... OK`.
- ADD, ABS, CLZ and POPCOUNT give correct results *when the opcode is held stable* (probe lines `ADD`,
  `ABS`, `CLZ`, `POP`).

## E. The `STA` repository (to be absorbed into `docs/STA_REPORT.md`)

1. `designs/alu32/src/alu32.v` is a **different design**: 7 ops on a 3-bit opcode, with shift by a
   constant 1. It is not the ALU in `32bit-RTL-To-GDS`.
2. `opensta/run_sta.tcl`:
   - reads `sky130.lib`, which does not exist in the repo and is not a real file name in the PDK;
   - calls `read_verilog` on the **RTL**. OpenSTA needs a gate-level netlist, so `link_design` would fail.
3. `automation/extract_metrics.py` parses `timing.rpt`, which is never generated.
4. `final_metrics/metrics_template.md` is an empty table.
5. The README claims multi-corner STA, timing closure, clock-skew optimisation and physical verification,
   but the repo has no reports, logs or results for any of them.
6. `designs/alu32/config.json` uses OpenLane-1-style keys (`PL_TARGET_DENSITY`, `RUN_CTS`) and points to
   the 7-op design.

## F. What carries forward

**Nothing from the legacy RTL is reused.** `legacy/` is kept for history and for this audit only. The new
design starts from `docs/BRIEF.md` Part A. Every bug above is checked by the new testbench and formal
proofs as a regression class:

| Legacy bug | Checked in the new design by |
|---|---|
| Decode correctness (A1) | Formal full-ALU equivalence |
| Back-to-back ops (A2) | Random stream with opcode changes every cycle |
| Flag timing (A3) | Scoreboard compares flags in the same cycle as `y` |
| `valid_out` (A4) | Formal latency protocol proof |
