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

---

## Bugs found by verification
(Phase 3 fills this in.)
