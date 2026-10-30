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

(Phase 3 adds bugs found by cocotb and formal.)
