# Design decisions

Format for each entry: **context → options → choice → evidence**. Newest at the bottom.

---

## D-001 — Work in a separate clone, mounted into the tool container
- **Context:** all EDA tools run inside the Docker container `iic-osic`, which originally mounted only
  `~/vlsi`. `~/vlsi` is itself a git repo, so cloning this project inside it would nest one repo in another.
- **Options:**
  1. Clone under `~/vlsi` and ignore it there.
  2. Clone to `~/projects` and add a second container mount.
- **Choice:** option 2 (user's choice). `~/projects` → `/foss/projects`. The container was recreated with
  that mount; no data was lost because all designs live on the host.
- **Evidence:** `docker exec iic-osic bash -lc 'ls /foss/projects'` lists `32bit-RTL-To-GDS`.

## D-002 — LibreLane instead of OpenLane
- **Context:** the brief says "librelane (or openlane)". The image ships LibreLane 3.1.0.dev3 and no
  `openlane`.
- **Options:**
  1. Install OpenLane 2 separately.
  2. Use LibreLane.
- **Choice:** LibreLane. It is the maintained successor of OpenLane 2, has the same configuration model,
  and is already installed. No extra installs are needed.
- **Evidence:** `results/env_check.txt`.

## D-003 — yices as the SMT solver for SymbiYosys
- **Context:** the brief asks for a solver (`z3`/`boolector`/`yices`). Only `yices-smt2` 2.7.0 is
  installed.
- **Options:**
  1. Ask to install z3 or boolector.
  2. Use yices.
- **Choice:** yices. It is one of the listed acceptable solvers and is a strong default for `smtbmc`.
  Yosys's built-in `abc pdr` engine is also available as a second engine if a proof struggles.
- **Evidence:** `results/env_check.txt`.

## D-004 — cocotb-coverage installed in a repo-local venv
- **Context:** `cocotb-coverage` was the only missing tool. The brief prefers pip inside a venv and
  forbids sudo.
- **Options:**
  1. A system pip install.
  2. A venv with `--system-site-packages`.
- **Choice:** option 2, `.venv/` in the repo (git-ignored, created inside the container), user-approved.
  It pins `cocotb-coverage==2.0`, the first release that supports cocotb 2.x (it requires `cocotb>=2.0`),
  and reuses the image's cocotb 2.0.1.
- **Evidence:** `results/env_check.txt` shows `cocotb 2.0.1` and `cocotb-coverage 2.0` from
  `.venv/bin/python`.

## D-005 — Audit claims are backed by a reproducible probe simulation
- **Context:** rule 1 forbids hand-typed results. The audit makes claims about the legacy design's
  behaviour.
- **Choice:** commit `legacy/tb_probe.v` and `scripts/legacy_probe.sh`. Every behavioural claim in
  `docs/AUDIT.md` quotes a line from `results/legacy_probe.txt`.
- **Evidence:** `scripts/legacy_probe.sh` reproduces the log.

## D-006 — Latency definition with registered inputs and outputs (spec clarification)
- **Context:** BRIEF A2 says "inputs and outputs are registered (1-cycle latency)". With both banks
  registered, a result reaches the output register one edge after the input register captures it. At the
  ports, that is 2 edges after `in_valid` is sampled, so the brief's number was ambiguous.
- **Options:**
  1. Register inputs and outputs, and define latency at the ports as 2 (PIPE=1: 3).
  2. Register only the outputs, keep "1 cycle", and accept port-to-register timing paths.
- **Choice:** option 1, chosen by the project owner on 2026-10-30. It keeps the brief's real intent:
  STA sees register-to-register paths, so the adder comparison isn't polluted by I/O constraints.
- **Evidence:** `docs/SPEC.md` section 2 (definition + WaveDrom). Phase 3's formal protocol proof will
  check L = 2 / 3.

## D-007 — Zbb test vectors: spec definitions + Spike (spec clarification)
- **Context:** Phase 1 asks to test the model against "the examples in the ratified RISC-V Zbb
  specification". The ratified text (`riscv-isa-manual` `src/unpriv/zbb.adoc` and `zb.adoc`, checked at
  commit `8fb3965fe4b5`) has **no numeric examples**. It gives a Sail "Operation" block per instruction,
  plus `strlen`/`strcmp` assembly in `bitmanip-examples.adoc`. A literal reading of the brief is
  impossible.
- **Options:**
  1. Hand vectors from the definitions only.
  2. Hand vectors, plus the strlen/strcmp idioms as tests, plus a cross-check against Spike, the RISC-V
     reference simulator.
- **Choice:** option 2, chosen by the project owner. Spike is an implementation written by others, so
  the check is independent in a way hand vectors can't be.
- **Evidence:**
  - `model/test_alu_ref.py`: hand vectors cite `zb#insns-*`; `test_strlen_idiom` and `test_strcmp_idiom`.
  - `results/model_xcheck.json`: 8,572 vectors over 27 ops, PASS. The vector count comes from the script.
  - **Mutation check:** a deliberately broken local copy of the model (MIN made unsigned; ORC.B testing
    only 7 bits per byte) made the cross-check report FAIL with mismatches in exactly those two ops, and
    made pytest fail. So the check really compares.
  - **Limitation:** Spike has no flags and no illegal-opcode concept, so only `y` is cross-checked.
    Flags and illegal opcodes are covered by the pytest cases.

## D-008 — Flag semantics; SUB carry means "no borrow"
- **Context:** RISC-V has no flags. The brief defines flags for ADD/SUB (N, Z from `y`; C = V = 0
  elsewhere) but leaves the sense of C on SUB open. P6 will reuse this ALU, so the choice must be fixed
  and documented.
- **Options:**
  1. C = carry-out of `a + ~b + 1` ("no borrow", ARM/6502).
  2. C = borrow (x86), i.e. the inverted carry-out.
- **Choice:** option 1, chosen by the project owner. It is the shared adder's raw carry-out, so no
  extra inverter is needed. V is the two's-complement overflow for both ADD and SUB. SLT(U) and
  MIN/MAX(U) report C = V = 0 even though they use the adder internally. An illegal opcode gives
  `y = 0`, so Z = 1.
- **Evidence:** `docs/SPEC.md` section 4; `model/test_alu_ref.py::test_flags`, `test_properties_binary`
  (`sub.c == (a >= b)`) and `test_c_v_zero_for_non_add_sub`.

## D-009 — Opcode encoding
- **Context:** the brief fixes 27 ops on a 5-bit opcode but not the encoding.
- **Options:**
  1. Arbitrary or alphabetical order.
  2. Reuse RISC-V funct3/funct7 bits (they don't fit in 5 bits for Zbb).
  3. RV32I first, then Zbb grouped by the hardware unit that executes the op.
- **Choice:** option 3: codes 0–9 RV32I, 10–13 adder-based Zbb, 14–16 logic, 17–18 rotates, 19–21
  count, 22–26 byte/extend, 27–31 illegal.
  - Grouping by unit keeps the unit-select logic small.
  - Illegal codes form one contiguous block (`op >= 27`), so detecting them is a single comparison.
- **Evidence:** `docs/SPEC.md` section 3; `model/alu_ref.py` `OPCODES`;
  `model/test_alu_ref.py::test_opcode_table`. Phase 2 will add a check that `rtl/alu_pkg.sv` matches.

## D-010 — Reset and output-hold policy
- **Context:** the brief names `rst_n` but doesn't define reset scope or what the outputs do when no
  operation is in flight.
- **Options:**
  1. Reset every register.
  2. Reset only the valid pipeline.
  3. Data registers load every cycle.
  4. Data registers load only when valid.
- **Choice:**
  - `rst_n` is active-low, asserted asynchronously and released synchronously. It resets **only the
    valid bits**.
  - Data registers have no reset and load only when their stage is valid; otherwise they hold.
  - Outputs are defined only while `out_valid = 1`.
- **Why:** resettable flops are larger. Holding data stops toggling on idle cycles, which shows up in
  the activity-annotated power numbers (Phase 4). That trade-off is measured, not assumed.
- **Evidence:** `docs/SPEC.md` section 2. It will be verified in Phase 3 (protocol proof; the scoreboard
  only compares when `out_valid = 1`).

## D-011 — Golden model style and independence
- **Context:** BRIEF A3 requires the model to be written independently of the RTL.
- **Choice:**
  - `model/alu_ref.py` is pure Python on unsigned ints, transcribed from the ratified Operation blocks
    (anchors cited per function).
  - It was written before any RTL exists.
  - It uses the straightforward scan or loop form of each definition (e.g. CLZ scans bits), never the
    tree structures the RTL will use. So a structural bug in the RTL can't be copied into the reference.
  - Opcode numbers are the only shared fact with the RTL; they are checked, not shared code.
- **Evidence:** `model/alu_ref.py`; `results/model_xcheck.json`.

## D-012 — SystemVerilog subset, and `ADDER` as an integer code
- **Context:** the RTL must be accepted by Verilator (lint and cocotb), Icarus (cocotb, BRIEF A3) and
  Yosys (LibreLane synthesis, SymbiYosys). The brief asks to check Yosys SV support early.
- **Probe:** small test modules in `sim_build/probe/` (not committed) using a package, `logic`,
  `always_ff`/`always_comb`, `for (genvar …)` with computed indices, unpacked arrays of packed
  vectors, and a string `ADDER` parameter selecting logic in `generate`.

  | Tool | Result |
  |---|---|
  | Verilator 5.050 | Accepts all of it. |
  | Yosys `read_slang` | Accepts all of it. The parameter really switches the logic (KS → `$add`, otherwise `$sub/$xor/$or`). |
  | Yosys built-in `read_verilog -sv` | Rejects `parameter string` and `import` inside a module. |
  | Icarus 14.0-dev | Parses everything, and honours string parameters given as **literals**. But it **cannot pass a string parameter from a parent module to a child**: `child #(.N(N))` fails with "Unable to bind variable", whether typed, untyped, renamed, via a localparam, or positional. |

- **Options:**
  1. String `ADDER`; drop Icarus. That breaks BRIEF A3, which requires cocotb on Icarus and Verilator.
  2. Choose the architecture with `` `define `` macros. That is preprocessor-driven and hides the choice
     from the parameter interface.
  3. **Integer `ADDER`** with named constants `alu_pkg::ADDER_RCA … ADDER_BEH`.
- **Choice:** option 3.
  - **Verified:** integer parameters pass parent → child and `-P`/`-G` overrides work in Icarus,
    Verilator and slang. Icarus selected the correct generate branch in simulation.
  - **Names:** they stay the brief's names everywhere a person types them. `scripts/adders.py` maps
    name → code, and `scripts/check_opcodes.py` checks that table against `alu_pkg.sv`.
  - **Yosys:** all Yosys use goes through slang (`USE_SLANG` in LibreLane, `read_slang` in checks and
    SBY). The built-in frontend's gaps therefore don't constrain the RTL.
  - **Further rules:** package imports go inside module bodies; one module per file (Verilator
    `DECLFILENAME`).
- **Impact on the brief:** the selector is still "parameter ADDER" with the 8 architectures in the A2
  table. Only its type is int instead of string. This is reported to the owner in the Phase 2 PR.
- **Evidence:** the probe outputs above (reproducible from the commands in the Phase 2 commit message);
  `results/adder_smoke.txt` (Icarus elaborates all 8 codes); `scripts/check_opcodes.py` PASS.

## D-013 — Where the PIPE=1 register goes
- **Context:** BRIEF A2: "`PIPE=1` adds a register after the adder/shifter stage". Stage S1 contains
  the adder, its comparison select (SLT/MIN/MAX need the adder result plus `a`/`b`), the shifter and
  the short "misc" units.
- **Options:**
  1. Register the raw adder outputs. MIN/MAX would then also need `a0`/`b0` registered: 64 extra
     flip-flops.
  2. Register each unit's *final* result: `r_add` (after the comparison mux), `r_shift` and `r_misc`,
     plus `sel`, C, V and illegal.
  3. Register only the muxed `y` (that is just a deeper output register and doesn't split anything).
- **Choice:** option 2, in `rtl/alu_top.sv` `g_pipe`.
  - About 102 data flip-flops. S1 = adder + compare mux (the critical path); S2 = 3:1 mux + zero detect.
  - The stages are deliberately unbalanced: the point of PIPE=1 is to take the final mux and
    flag logic off the adder path.
  - Phase 4 will measure whether it pays off.
- **Evidence:** `results/lint_summary.json` and `results/synth_check.json` (PIPE=1 configs PASS).
  Latency L=3 will be proven formally in Phase 3.

## D-014 — One shared `~b` inverter
- **Context:** SUB/SLT/SLTU/MIN/MAX/MINU/MAXU need `a + ~b + 1`; ANDN/ORN/XNOR need `~b`. The Zbb spec's
  implementation hint suggests reusing the subtraction inverter.
- **Choice:** `bx = inv_b ? ~b0 : b0` feeds both the adder and the AND/OR/XOR unit. AND and ANDN then
  share one AND gate row, and so on.
- **Evidence:** `rtl/alu_top.sv` (`inv_b`, `bx`). Correctness will be proven by the full-ALU
  equivalence in Phase 3.

## D-015 — CTZ through the CLZ tree
- **Context:** BRIEF A2: "CTZ is a bit reversal followed by the CLZ tree."
- **Choice:** a single `clz` instance whose input is `(op == CTZ) ? rev32(a) : a`. Bit reversal is pure
  wiring; the only cost is a 32-bit 2:1 mux, instead of a second tree.
  - `clz` is a recursive halving tree (`rtl/clz_tree.sv`) with log₂32 = 5 mux levels.
  - All-zero input gives 32, per `zb#insns-clz`.
- **Evidence:** `rtl/clz.sv`, `rtl/clz_tree.sv`, `rtl/alu_top.sv`.

## D-016 — Shifter as a funnel shifter with bit reversal
- **Context:** BRIEF A2: one shared logarithmic barrel shifter for SLL/SRL/SRA/ROL/ROR, with left shifts
  via bit reversal.
- **Options:**
  1. A separate rotate unit.
  2. A 64-bit double-width shifter.
  3. A 63→32 funnel right shifter, where the fill bits select the operation: 0 for SRL, sign for SRA,
     `a[30:0]` for ROR.
- **Choice:** option 3.
  - Left operations reverse the input and the output: `SLL = rev(SRL(rev a))`,
    `ROL = rev(ROR(rev a))`.
  - Five 2:1 mux stages (16, 8, 4, 2, 1), with each stage only as wide as later stages can use
    (63→47→39→35→33→32).
  - Rotate-by-0 gives `a` naturally.
- **Evidence:** `rtl/shifter.sv`.

## D-017 — Formal property style
- **Context:** SymbiYosys must read the RTL through yosys-slang (D-012). Not every SystemVerilog
  assertion form is supported by every frontend.
- **Probe:** a 2-stage valid delay with three harness styles, run with `sby` (`sim_build/probe_formal/`,
  not committed).

  | Style | Result |
  |---|---|
  | (a) shadow registers + immediate `assert` in `always_comb`, reset forced by `assume` gated by an `init` register | PASS |
  | (b) `$past(x, 2)` in `always_ff` | PASS |
  | (c) a deliberately wrong delay | **FAIL** with a counterexample, so the property is not vacuous |

- **Choice:** style (a), immediate assertions with explicit shadow pipelines.
  - It reads like the hardware, works with any frontend, and the shadow pipeline doubles as
    documentation of the timing contract.
  - `$past` remains available.
- **Evidence:** `formal/alu_equiv.sv`, `formal/protocol.sv`.

## D-018 — Formal equivalence strategy
- **Context:** BRIEF A3 asks for three formal checks:
  - a per-adder miter;
  - full-ALU equivalence against a separate behavioural reference, with all ops proven;
  - the `out_valid` latency protocol.

  Risk: 32-bit equivalence that includes a shifter, CLZ and CPOP can be slow for SAT.
- **Choice:**
  - **Adder miters** (`formal/adder_miter.sv`): combinational, `assert({cout,sum} == a+b+cin)`,
    32 bits, one task per architecture.
  - **ALU equivalence** (`formal/alu_equiv.sv`):
    - `alu_top` runs next to a shadow pipeline with the SPEC timing, feeding
      `formal/alu_ref_beh.sv`.
    - The reference is written from SPEC sections 3–5 with plain operators and literal opcodes; it
      shares no module or package with the RTL, so an opcode-encoding error would also be caught.
    - Asserts `out_valid == expected_valid` and, when valid, equal `y`/`flags`/`illegal_op`.
    - Reset is assumed only in cycle 0; it may recur at any time.
    - One task per ADDER × PIPE (16), mode `prove` (k-induction, depth 6).
  - **Protocol** (`formal/protocol.sv`): `out_valid(t+L) == in_valid(t)` via an L-deep shadow shift
    register, plus "no `out_valid` in the first L cycles after reset", for PIPE 0 and 1.
- **Op grouping (the planned fallback) was not needed.** Every task closed as a whole by k-induction
  with smtbmc/yices. Per-task times are in `results/formal/summary.json`.
- **Mutation checks** (local copies; the real RTL was not touched):
  - one KS prefix index shifted → adder miter FAIL with a counterexample trace;
  - SUB carry inverted → ALU equivalence FAIL (the `flags` assertion);
  - `out_valid` taken one stage early → protocol FAIL.

  So no proof is vacuous.

## D-019 — Simulation vector budget and constrained-random stimulus
- **Context:** BRIEF A3 requires directed corners and ≥10⁶ constrained-random vectors per adder
  configuration, with Verilator used for speed.
- **Budget:**

  | Simulator | Configurations | Random vectors |
  |---|---|---|
  | Verilator | 8 ADDER × PIPE=0 | 1,000,000 each — the gate |
  | Verilator | 8 ADDER × PIPE=1 | 100,000 each |
  | Icarus | 8 ADDER × PIPE=0 | 20,000 each, to show both simulators agree |

  Every run also executes the full directed test. Formal equivalence covers every configuration
  exhaustively, so the extra PIPE=1 and Icarus vectors are cross-checks, not the proof.
- **Stimulus** (`tb/alu_tb.py`):
  - **Opcodes:** uniform over the 27 legal opcodes; illegal codes about 3%.
  - **Operands:** a weighted mix of zero, small ±, INT_MAX, INT_MIN, values near the extremes,
    single-bit, fixed patterns, long zero runs at either end (for CLZ/CTZ), and uniform random.
  - **Shift/rotate `b`:** biased to 0/1/31 with random upper bits.
  - **Bubbles:** about 10% of cycles.
  - **Reset:** a mid-stream reset roughly every 250k vectors.
- **Seeds:** set explicitly (`--seed`, default 20261030), passed to the TB as `ALU_SEED`, and recorded
  in every result file.
- **Throughput** (measured): 10k vectors plus the directed test takes a few seconds on Verilator,
  build included, so 1M per configuration is minutes, not hours.
- **Mutation check of the bench** (local, not committed):
  - SUB carry inverted → FAIL ("NZCV=0100, expected 0110" on `SUB 0,0`);
  - ORC.B testing only 7 bits per byte → FAIL.

## D-020 — CI tooling and scope
- **Context:** BRIEF Phase 3 asks for GitHub Actions running lint, a reduced sim and formal, not the
  full flow. The local tool image (iic-osic-tools) is 16 GB, too large for a hosted runner.
- **Options:**
  1. Pull the iic-osic image in CI.
  2. Distro packages (too old: the RTL needs a recent Icarus/Verilator and the slang plugin).
  3. YosysHQ OSS CAD Suite, which bundles Yosys + yosys-slang, SymbiYosys, yices, Verilator and Icarus.
- **Choice:** option 3.
  - `YosysHQ/setup-oss-cad-suite` v4, pinned to release **2026-10-14** (more than 2 weeks old when
    chosen).
  - Python 3.12 with `cocotb==2.0.1`, `cocotb-coverage==2.0` and `pytest`.
  - Every action is pinned to a commit SHA.
- **CI runs:**
  - `make model-test` (Spike is absent, so `test_spike_xcheck` skips with its reason);
  - `opcodes-check`;
  - `lint` (all 24 configs);
  - `sim-ci`: Verilator 20k vectors for BEH, KS and RCA (PIPE 0) + BEH PIPE 1; Icarus 5k for BEH;
  - `formal-ci`: all 8 adder miters, both protocol proofs, and ALU equivalence for BEH and KS at
    PIPE 0/1.
- **Why the formal subset:** the full 16-task ALU equivalence takes minutes per task on a 2-core runner.
  The full set runs locally under `make verify`, and its results are committed.
- **Limitation:** CI tool versions differ from the container. A CI-only failure is investigated, not
  masked.
- **First CI runs:** OSS CAD Suite gave Verilator 5.053-devel, Yosys 0.70, SBY 0.69 and Icarus
  14.0-dev (newer build).
  - Run 41066356427 failed lint with a check the container's Verilator 5.050 lacks: `SIMILARNAME` on
    `p`/`P` in the four prefix adders.
  - The fix was a rename (`p` → `pb`), not a waiver. To see the message, `scripts/lint.py` now prints
    the warning text for failing configurations.
  - Run 41067482198 was green: model 161 passed + 1 skipped (Spike), lint 24/24, sim-ci 5/5 at 100%
    coverage, formal-ci 14/14.

## D-021 — RTL coding style adjusted for an Icarus 14.0-dev evaluation problem
- **Context:** the first Icarus cocotb run of `alu_top` failed on SLL, SRA, ROL, ROR and CTZ, while
  Verilator passed the same test. Isolating it:
  - `shifter` alone in Icarus is correct.
  - Package constants inside `alu_top` print correctly (`OP_SLL = 2`).
  - Inside `alu_top`, comparisons written **inside port connections**
    (`.left((op0 == OP_SLL) | …)`, `.arith(op0 == OP_SRA)`) and the `sel1` select (an `always_comb`
    `if` + multi-item `case`) evaluated wrongly: `left = 0` and `sel1 = MISC` for `op0 = 2`.
  - The same comparison as a plain `assign`, an `always_comb`, or against a literal gave the right
    value in the same module. A standalone copy of the same `case` structure was also right.
  - So this is an Icarus problem, not an RTL logic bug. The design passed Verilator, synthesis, and
    (later) formal equivalence.
- **Options:**
  1. Drop Icarus. That breaks BRIEF A3.
  2. Keep bisecting the simulator.
  3. Recode the decode in the form shown to evaluate correctly in all tools.
- **Choice:** option 3, in `rtl/alu_top.sv`:
  - a one-hot decode of the registered opcode into named `d_*` wires with plain `assign`s;
  - no logic inside port connections;
  - AND-OR one-hot muxes for `r_add`/`r_misc`;
  - ternary chains for `sel1`/`y_next`.

  This is also a common, readable RTL style, and it makes the decode visible in waveforms.
- **Evidence:** after the change, Icarus PASS (`results/sim/icarus_*`), Verilator PASS, lint 24/24
  clean, synth-check 16/16, and formal equivalence on all configs (`results/formal/summary.json`).
- **Follow-up:** this can be reported upstream to Icarus with the minimal case. It is not a project
  blocker.

## D-022 — Floorplan policy for the sweep: fixed utilisation
- **Context:** BRIEF A4: "Keep die size and utilisation policy fixed across architectures so the
  comparison is fair." Two readings were offered: one fixed die for all, or a fixed utilisation
  percentage. The project owner chose **fixed utilisation** (2026-10-30).
- **Choice** (`flow/config.template.json`):
  - `FP_SIZING relative`, `FP_CORE_UTIL 40`, `PL_TARGET_DENSITY_PCT 50` for every architecture and every
    period.
  - All other settings at LibreLane defaults: the same `base.sdc` (input/output delay = 20% of period,
    default clock uncertainty), the same CTS and resizer settings.
  - The die therefore grows with each architecture's cell area. Die and core area are reported per
    architecture.
- **Consequence:** wirelength comparisons include the effect of die size, which is the real cost of a
  bigger adder.
- **First measured run** (`runs/BEH_P0_T10.00`): about 10 min wall and 0.9 GB peak RAM per run, so the
  sweep runs 3 architectures in parallel on this 6-core, 7 GB machine. At 10 ns, BEH had setup WS
  −10.17 ns at `max_ss_100C_1v60` and −0.65 ns at `nom_tt_025C_1v80`. The critical path is an
  input-register → output-register chain of `a311`/`o311` cells: the synthesiser's mapping of `a + b`
  looks like a ripple carry. D-026 tests that.

## D-026 — ABC structure experiment: the default flow destroys the adder architectures
- **Question** (BRIEF A4 "Structure check"): does ABC keep the hand-written prefix trees?
- **Method** (`scripts/abc_exp.py`, `flow/adder_wrap.sv`):
  - The adder alone, between input and output registers, is synthesised with the sweep's exact
    LibreLane settings in two variants:
    - **default:** flattened, LibreLane's default `AREA 0` ABC script;
    - **preserved:** slang `--keep-hierarchy` plus `keep_hierarchy` on `pg_black*`, `pg_gray*`,
      `cla4_unit*` and `adder_rca*`, so ABC maps each cell separately.
  - The worst register-to-register path is measured with OpenSTA: tt_025C_1v80 liberty, ideal clock,
    no wire parasitics.
  - The flow's own pre-PnR `max.rpt` was **not** used for this, because for fast adders its worst path
    is an output-port path set by the 20% I/O delay (seen in the first trial).
- **Result** (`results/flow/abc_experiment.json`; table generated from that file):

| Arch | Default: depth | Default: r2r delay (ns) | Default: area (µm²) | Preserved: depth | Preserved: r2r delay (ns) | Preserved: area (µm²) |
|---|---|---|---|---|---|---|
| RCA | 32 | 12.7865 | 2842.7 | 32 | 12.7865 | 2842.7 |
| CLA4 | 22 | 6.1088 | 3009.1 | 15 | 2.6773 | 3803.6 |
| CSLA | 32 | 12.7865 | 2842.7 | 11 | 5.1996 | 3827.4 |
| BK | 20 | 6.2303 | 2969.1 | 10 | 2.5135 | 3316.9 |
| KS | 17 | 4.5047 | 3088.0 | 6 | 1.7392 | 4307.9 |
| SK | 21 | 6.0724 | 2996.6 | 7 | 2.0776 | 3633.5 |
| HC | 16 | 4.4413 | 3066.7 | 7 | 1.9001 | 3633.5 |
| BEH | 20 | 5.9127 | 2979.1 | 20 | 5.9134 | 2979.1 |

- **Findings:**
  - **Preserved,** logic depth follows the theory: KS < SK = HC < BK < CSLA < CLA4, prefix depth
    plus the pre/post cells. Delays order the same way.
  - **Default ABC** (area script, with `amap` and repeated balance/rewrite) turns every prefix adder
    into a 16–22-deep chain, 2.3–3.5× slower and 12–40% smaller.
  - **CSLA under default synthesis is identical to RCA** (same cells, area and delay): the duplicated
    cin=0/cin=1 adders and the select logic were merged away.
  - **BEH:** Yosys first maps `+` to a Brent–Kung `$lcu` (`_90_lcu_brent_kung` in the log), and ABC
    then restructures that too (depth 20, ~5.9 ns).
- **Consequence:** a default-flow PPA sweep mostly measures what ABC built, not the architectures. This
  is why D-027 adds a structure-preserved sweep.

## D-027 — Two physical-design sweeps: default flow and structure-preserved flow
- **Context:** D-026 shows that the stock flow erases the architectural differences, while the brief's
  question is "which adder should this ALU use at a given frequency target, and why?".
- **Options:**
  1. Default-flow sweep only.
  2. Preserved sweep only.
  3. Both.
- **Choice:** option 3, chosen by the project owner on 2026-10-30.
  - The **default** sweep (`results/flow/sweep/`) shows what a stock flow delivers.
  - The **preserved** sweep (`results/flow/sweep_preserved/`, run tags `*_preserved`) uses identical
    settings plus D-026's `keep_hierarchy` list, and shows what each architecture can deliver.
  - The recommendation (Phase 5) is based on the preserved sweep. Both sets are reported.
- **Implementation:** `scripts/flow_run.py` `VARIANTS`, `scripts/sweep.py --variant preserved`. The
  preserved sweep runs with 2 parallel jobs alongside the default sweep's 3 (5 × ~0.9 GB peak RAM on a
  7 GB machine).

## D-028 — Enable timing repair after global routing (first sweep attempt discarded)
- **Symptom:** in the first sweep attempt the slowest-corner slack did not converge. RCA failed at
  15, 22.75 and 26 ns with WS −7.6, −3.1 and −3.9 ns at `max_ss_100C_1v60`: the path got slower as
  the clock relaxed.
- **Diagnosis** (`runs_v1_no_post_grt_repair/RCA_P0_T26.00`):
  - The post-CTS resizer did repair setup, from −6.781 ns to +0.060 ns, but against *placement-estimated*
    parasitics.
  - After global and detailed routing, the real wires added about 4 ns at `max_ss`, and 549 max-slew
    violations remained.
  - LibreLane's Classic flow has `RUN_POST_GRT_RESIZER_TIMING = false` and
    `RUN_POST_GRT_DESIGN_REPAIR = false` by default, so nothing repairs after routing.
  - Every run therefore lands about 4 ns short of whatever target it is given. The "minimum period"
    would measure the unrepaired routing penalty, not the adder.
- **Choice:** enable both steps in `flow/config.template.json` for every architecture and both
  variants. Repair then sees global-routing parasitics, which is standard practice when signing off at
  a slow corner.
- **Consequences:**
  - The runs made before this change (about 1.5 h of compute) are archived unchanged in
    `runs_v1_no_post_grt_repair/` (git-ignored) and are not used.
  - Both sweeps were restarted.
  - The ABC experiment (synthesis only) is unaffected.

## D-029 — Setup-repair margin of 12% of the clock period
- **Symptom after D-028:** post-global-routing repair ran, but final timing at `max_ss` still came out
  about 2 ns short of what the repair step reported. RCA at 22 ns: repair +0.029 ns (all violations
  fixed by its estimate), final WS −2.080 ns (`runs_v2_post_grt_repair_no_margin/RCA_P0_T22.00`).
- **Cause:**
  - The resizer works from placement or global-routing parasitic *estimates*. Signoff STA uses
    detailed-routing extracted RC.
  - The intermediate STA steps during PnR evaluate only the default corner (`nom_tt`), so the
    optimism at the slow corners is invisible until signoff.
  - The error was about 9.5% of the period at `max_ss`. Without margin, every run lands that much
    short, and the sweep drifts toward the design's *unrepaired* delay.
- **Choice:**
  - `PL_RESIZER_SETUP_SLACK_MARGIN` = `GRT_RESIZER_SETUP_SLACK_MARGIN` = **0.12 × CLOCK_PERIOD**,
    set per run by `scripts/flow_run.py` (`SETUP_MARGIN_FRAC`).
  - The same rule applies to every architecture and both variants, so the comparison stays fair.
  - This is the usual over-constraining of optimisation against estimate error. The cost is somewhat
    more repair area, which is reported.
- **Test** (`runs/RCA_P0_T22.00`, margin 2.64 ns): repair reached +0.919 ns (it hit RCA's limit), and
  the final WS at `max_ss` was −0.762 ns, versus −2.080 ns without margin. The estimate-to-final gap
  drops from 2.1 to 0.76 ns. RCA at 22 ns is simply just below what RCA can do.
- The runs made without margin are archived in `runs_v2_post_grt_repair_no_margin/` (git-ignored) and
  not used. Both sweeps were restarted with D-028 + D-029.

---

## Bugs found by verification

### Phase 2 (found by the early adder smoke test, before Phase 3)

**B-001 — CLA4 carry-out wrong (padding used p = 0).**
- **Symptom:** `scripts/adder_smoke.sh` reported 75,701 of 151,078 vectors wrong for CLA4 only. Sums
  were correct; `cout` was always 0.
  - Example: `W=8 a=00 b=ff cin=1 got=000 exp=100`.
- **Cause:**
  - At the top lookahead level, 2 real groups are padded to a 4-input `cla4_unit`.
  - Padding was tied to `g = 0, p = 0`.
  - The unit's group propagate is `gp = &p`, so any padded 0 forced `gp = 0`.
  - `cout = G | P & cin` then lost the propagate term.
- **Fix:** pad with the identity of the (G, P) operator, `g = 0, p = 1` (`rtl/adders/adder_cla4.sv`).
- **Verified:** adder smoke CLA4 PASS (151,078 vectors, 0 errors); Verilator `-Wall` gives 0 warnings
  at W = 8/16/32/64.
- **Lesson:** padding must be the operator's identity element. It goes in LEARNING.md.

### Phase 3 (cocotb + formal)

**No functional RTL bugs were found.**
- The full regression (`results/sim/`) and every proof (`results/formal/summary.json`) passed on the
  first complete run.
- The only failure was the Icarus-only mis-evaluation described in **D-021**. That was a simulator
  problem, not an RTL logic error: Verilator, synthesis and formal equivalence all agreed the original
  RTL was correct. The RTL was recoded so every tool evaluates it the same way.
- **This is not because the checks are weak.** Each check was mutation-tested and caught its injected
  fault (D-018, D-019).
- **Testbench issue found and fixed during the run:** the first 1M-vector runs checked 999,998 results
  per configuration, because the mid-stream reset flushes 2 in-flight operations. The bench now issues
  until exactly `ALU_VECTORS` results are checked, replacing flushed operations. It fails if the count
  is not exact.
