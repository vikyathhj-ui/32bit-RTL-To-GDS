# P1 — `rv32-alu-ppa-explorer`

**Title:** RV32 ALU PPA Explorer: 7 adder architectures, formally verified, taken RTL to GDS on SKY130.

Reworks `32bit-RTL-To-GDS` and absorbs `STA`. Target roles are digital design, physical design and STA (TI DDE, NXP front-end).

P6 (`lp-rv32-mcu`) reuses this ALU, so keep the interface clean and documented.

## Part A — Design specification (read this yourself)

### A1. Why this stands out
Most students write "a 32-bit ALU". This project answers a question real architects ask: *which adder architecture should this ALU use at a given frequency target, and why?* It answers it with post-route data from every corner, formal proofs and activity-based power. On top of that it adds a RISC-V Zbb bit-manipulation ALU, which reads as current industry ISA work.

### A2. Functional spec

**Ports:**
- `clk`, `rst_n`
- `in_valid`, `op[4:0]`, `a[31:0]`, `b[31:0]`
- `out_valid`, `y[31:0]`, `flags{N,Z,C,V}`

**Timing:** inputs and outputs are registered (1-cycle latency) so that STA sees reg-to-reg paths. An optional parameter `PIPE=1` adds a register after the adder/shifter stage (2-cycle latency).

**Operation set: 27 ops, 5-bit opcode, all defined in `rtl/alu_pkg.sv`:**
- **RV32I ALU (10):** ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND
- **Zbb subset (17):** ANDN, ORN, XNOR, CLZ, CTZ, CPOP, MIN, MAX, MINU, MAXU, SEXT.B, SEXT.H, ZEXT.H, ROL, ROR, REV8, ORC.B

**Behaviour rules:**
- Shift and rotate amounts use `b[4:0]`, as in RISC-V.
- Flags are defined for ADD/SUB. For other ops: N and Z from `y`, C = V = 0. Document this choice.
- Undefined opcodes give `y = 0` and assert an `illegal_op` output.

**Micro-architecture rules (resource sharing is part of the design story):**
- One shared adder serves ADD, SUB, SLT(U) and MIN/MAX(U) (compare by subtraction).
- One shared logarithmic barrel shifter serves SLL, SRL, SRA, ROL and ROR (left shift via bit reversal).
- CLZ uses a log-depth leading-zero tree; CTZ is a bit reversal followed by the CLZ tree.
- CPOP uses a compressor/adder tree.

**Adder core, selected by `parameter ADDER`:**

| Value | Architecture |
|---|---|
| `RCA` | ripple carry |
| `CLA4` | 4-bit carry-lookahead groups with group lookahead |
| `CSLA` | carry-select, 8-bit blocks |
| `BK` | Brent–Kung prefix |
| `KS` | Kogge–Stone prefix |
| `SK` | Sklansky prefix |
| `HC` | Han–Carlson prefix |
| `BEH` | behavioural `a + b`; the synthesiser's own mapping is the baseline |

Write each prefix adder with explicit generate/propagate cells, using `generate` loops rather than hand-unrolled code.

### A3. Verification spec
- **Golden model:** `model/alu_ref.py`, written independently of the RTL, with a bit-exact definition of every op.
- **Testbench:** cocotb on Icarus and Verilator.
  - Directed corners: 0, 1, −1, INT_MIN, INT_MAX, alternating bit patterns, shift amounts 0/1/31, and every op × flag edge.
  - At least 10⁶ constrained-random vectors per adder configuration (use Verilator for speed).
  - Self-checking: each test prints PASS/FAIL with a mismatch dump.
- **Functional coverage** (cocotb-coverage):
  - op × operand class (zero / positive / negative / max / min);
  - flag values per op;
  - shift amount bins;
  - CLZ/CTZ results 0..32.

  Target 100% of defined bins, with any unreachable bin justified in writing.
- **Formal (SymbiYosys):**
  1. **Equivalence:** for each adder architecture, a miter proves `adder(a,b,cin) == a+b+cin` for all inputs.
  2. **ALU equivalence:** the full ALU against a separate behavioural reference ALU, with all ops proven.
  3. **Protocol:** `out_valid` follows `in_valid` with exactly the configured latency.
- **Lint:** `verilator --lint-only -Wall` gives zero warnings; any waiver is inline with a justification.

### A4. Implementation spec (LibreLane, sky130A, `sky130_fd_sc_hd`)
- **Sweep:** for every `ADDER` value, find the **minimum clock period that closes timing at the slowest STA corner LibreLane reports**. Use a period sweep or binary search with 0.25 ns resolution. Keep die size and utilisation policy fixed across architectures so the comparison is fair.
- **Collect per run:** cell count, cell area, core area, utilisation, WNS/TNS (setup and hold) at every corner, fmax per corner, and the critical path (startpoint, endpoint, logic depth).
- **Power:**
  - Annotate switching activity from a realistic VCD made by a cocotb workload mix: 50% add/sub, 20% logic, 20% shift, 10% Zbb.
  - Use OpenSTA's `read_vcd`/`read_saif`, after checking which your installed version supports. If annotation isn't possible, use default activity and **label it as such**.
  - Report energy per operation = P × T.
- **Structure check:** ABC may restructure hand-written prefix trees. Compare logic depth and cell mix with ABC's default script against a structure-preserving setting (or check with `keep_hierarchy`). State in the report whether the architectural differences survived synthesis. This is an interview-grade insight.
- **Post-synth vs post-route:** report the delay degradation per architecture and explain it (fan-out and wiring of KS versus BK).
- **Signoff for the recommended configuration:** Magic + KLayout DRC clean, Netgen LVS clean, antenna clean, OpenROAD IR-drop report, and a KLayout GDS render image.

### A5. Deliverables
- `results/summary.json`, machine-generated and the **only** source of every number in README and resume.
- **Pareto plots:** fmax(slowest corner) vs area; energy/op vs delay; area vs architecture.
- **`docs/SPEC.md`:** functional spec, op table, interface timing diagram (WaveDrom JSON is fine).
- **`docs/MICROARCH.md`:** block diagram, resource sharing, adder theory (depth, fan-out, wire tracks per architecture).
- **`docs/PPA_REPORT.md`:** methodology, tables, plots, ABC finding, and the recommendation (which adder at which target and why).
- **`docs/STA_REPORT.md`:** the critical path of the chosen configuration at each corner, with a fix attempted and its effect. This replaces the old `STA` repo.
- **`docs/DECISIONS.md`**, **`docs/LEARNING.md`**, **`docs/INTERVIEW.md`**.
- **Plumbing:** one `make all` (lint → sim → formal → flow sweep → reports); GitHub Actions running lint, sim and formal (not the full flow).

### A6. Done when
- All 8 adder configs pass sim, coverage and formal.
- The sweep has completed for all of them.
- The recommended config is signoff-clean.
- The README's results table is generated from `summary.json`.
- You can answer every question in `INTERVIEW.md` without notes.

---

## Part B — Prompt for Claude Code

**How to use this:** paste this **entire file** (Part A and Part B) into Claude Code as one message. Part A is the binding spec. Claude saves the whole file as `docs/BRIEF.md` so later sessions can re-read it.

---

You are working in my existing GitHub repo `32bit-RTL-To-GDS` (owner `vikyathhj-ui`). Your job is to turn it into a professional, reproducible digital design project named `rv32-alu-ppa-explorer`: an RV32I+Zbb ALU with an adder-architecture design-space exploration taken through full RTL-to-GDS on SKY130 with LibreLane. I am a final-year ECE student. These projects are for VLSI design job applications (TI, NXP and similar), so quality, correctness and honesty matter more than speed.

### Non-negotiable rules
1. **Never fabricate or hand-type a result.** Every number in any doc must be produced by a script from a tool log or report, and stored in `results/summary.json` with the path of its source report. If a tool fails, report the failure; do not estimate.
2. **Never rewrite or backdate git history.** No force-push to `main`. Work on branch `rework/alu-ppa`.
3. **Commit protocol:**
   - Commit after every completed gate in PROGRESS.md, using Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `build:`, `ci:`).
   - The body says what changed, why, and how it was verified (command + result).
   - Keep the default `Co-Authored-By: Claude` trailer.
   - Push the branch after each commit. At the end of each phase, open a PR to `main` with `gh pr create`; its description summarises changes, verification evidence and open issues.
   - **Do not merge PRs. I merge.**
4. **Ask me before:** renaming the repo, changing visibility, archiving or deleting any repo (including `STA`), installing system packages, or any action outside this repo.
5. If a spec item is infeasible with the installed tools, stop, explain why, and propose the closest honest alternative. Do not quietly downgrade the spec.
6. Use `PROGRESS.md` as the single source of truth for status. Update it before every commit, so a fresh session can resume from "Read CLAUDE.md and PROGRESS.md and continue".
7. Explain as you go. For every design decision, add an entry to `docs/DECISIONS.md` (context → options → choice → evidence). Maintain `docs/LEARNING.md` (concepts I must understand, explained simply with references to the code) and `docs/INTERVIEW.md` (30+ likely interview questions, with answers using *this project's actual numbers*).

### Phase 0 — Setup and audit (one commit)
- **Environment check.** Run `which`/version for: `iverilog`, `verilator`, `yosys`, `sby`, `yosys-smtbmc` and a solver (`z3`/`boolector`/`yices`), `python3` with `cocotb` and `cocotb-coverage`, `librelane` (or `openlane`), `openroad`, `sta`, `magic`, `netgen`, `klayout`, and the sky130A PDK path (`PDK_ROOT`).
  - Print a table of found/missing.
  - If something is missing, stop and give me the exact install commands. Prefer pip/volare (or its successor ciel) inside a venv. Do not run sudo yourself.
- **Audit the existing repo.** List every bug and inconsistency in `docs/AUDIT.md`. Known issues to confirm: opcode decode bugs in `alu32_final.v`; ripple carry where "CLA" was claimed; no testbench; resume claims that cannot be reproduced (29 ops, 3,437 cells, 22,347 µm², 4.98 mW, −6.62 ns WNS on SS).
- **Create the repo files:**
  - `docs/BRIEF.md`: this entire message, saved verbatim;
  - `CLAUDE.md` with these rules, the repo layout, and the line "The binding spec is docs/BRIEF.md";
  - `PROGRESS.md` with every phase/gate below as checkboxes;
  - `.gitattributes` (`* text=auto eol=lf`);
  - `.gitignore` (runs/, sim_build/, *.vcd, __pycache__, .venv);
  - `LICENSE` (MIT).
- **Layout:**
  ```
  rtl/  model/  tb/  formal/  flow/  scripts/  results/  docs/  .github/workflows/
  ```
  Move the old RTL to `legacy/` and keep it; don't delete history.

### Phase 1 — Spec and golden model
- Write `docs/SPEC.md` from Part A2–A3 of `docs/BRIEF.md`, adding an op table with bit-exact definitions and an interface timing diagram.
- Write `model/alu_ref.py`, with Python unit tests checking it against hand-computed vectors and the examples in the ratified RISC-V Zbb specification.
- Part A of the brief is binding. If you think any part of it is wrong, say so and wait for my answer; do not silently change it.

Gate: model tests pass. Commit.

### Phase 2 — RTL
- `rtl/alu_pkg.sv` (opcodes), `rtl/alu_top.sv`, `rtl/adders/*.sv` (one file per architecture with a common interface), `rtl/shifter.sv`, `rtl/clz.sv`, `rtl/cpop.sv`.
- Synthesisable SystemVerilog that Yosys (with its SV frontend) and Verilator both accept. Check Yosys SV support early, and fall back to Verilog-2005 constructs where needed.
- `verilator --lint-only -Wall` is clean for every `ADDER` value.

Gate: lint clean for all 8 configs. Commit.

### Phase 3 — Verification
- cocotb testbench as specified: directed, then ≥10⁶ random vectors per config, then the coverage report.
- SymbiYosys: per-adder equivalence miter, full-ALU equivalence against a behavioural reference, latency protocol check.
- `make verify` runs everything and writes `results/verify_summary.json` (pass/fail and coverage %).
- Gate: 8/8 configs pass, coverage 100% (or each gap justified), all proofs PASS. Fix RTL bugs found, and record each in `docs/DECISIONS.md` under "Bugs found by verification".
- Add `.github/workflows/ci.yml` running lint, sim with a reduced vector count, and formal on push. Commit.

### Phase 4 — Physical design sweep
- `flow/config.json` template per architecture; `scripts/sweep.py` finds the minimum closing period at the slowest corner (0.25 ns resolution), with fixed die/utilisation policy.
- Parse LibreLane reports into `results/summary.json`: area, cells, utilisation, WNS/TNS setup and hold per corner, fmax per corner, critical path, logic depth.
- **Power:** generate the workload VCD from cocotb (mix: 50% add/sub, 20% logic, 20% shift, 10% Zbb); annotate in OpenSTA if supported, otherwise label as default activity. Energy/op = P × T.
- **ABC structure experiment:** default vs structure-preserving synthesis, comparing logic depth and cell mix per architecture.
- Post-synth vs post-route delay per architecture.
- Runs can be long: run them in the background, log to `runs/`, and never commit `runs/`.

Gate: all configs complete and `summary.json` is populated. Commit.

### Phase 5 — Signoff, reports, docs
- Pick the recommended config from the data (justify in DECISIONS.md). Get clean DRC (Magic + KLayout), LVS (Netgen) and antenna, plus an IR-drop report and a GDS render PNG.
- `scripts/plots.py` → Pareto plots in `results/plots/`.
- Write `docs/MICROARCH.md`, `docs/PPA_REPORT.md` and `docs/STA_REPORT.md` (critical path per corner, one fix attempted, and its measured effect).
- **README.md:**
  - one-paragraph pitch;
  - block diagram;
  - results table **auto-generated** from summary.json by `scripts/gen_readme_table.py`;
  - plots;
  - "Reproduce" with `make all`;
  - "Limitations" (simulation/flow only, no silicon; any labelled assumptions);
  - "AI assistance": "Developed with Claude Code; all results reproduced by Vikyath J with `make all`."
- Finalise `docs/LEARNING.md` and `docs/INTERVIEW.md`. The interview file must cover:
  - why prefix adders are log-depth;
  - KS vs BK fan-out and wiring;
  - why post-route changes the ranking;
  - setup vs hold and why hold matters at the FF corner;
  - what ABC did;
  - how the formal miter works;
  - coverage vs formal;
  - energy/op vs power.
- Generate `results/resume_bullets.md`: 3 bullets using only numbers from summary.json.
- Open the final PR.
- Then ask me whether to rename the repo to `rv32-alu-ppa-explorer` and archive `STA` (with a README pointer to `docs/STA_REPORT.md`).

Start with Phase 0. Work in plan mode first and show me the plan before editing files.
