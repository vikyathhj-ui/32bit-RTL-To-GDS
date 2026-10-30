# rv32-alu-ppa-explorer (repo: vikyathhj-ui/32bit-RTL-To-GDS)

**The binding spec is docs/BRIEF.md.** Part A is the design spec; Part B holds the working rules and
phases. Status lives in `PROGRESS.md`. To resume: "Read CLAUDE.md and PROGRESS.md and continue".

## Non-negotiable rules (from docs/BRIEF.md Part B)
1. **Never fabricate or hand-type a result.** Every number in any doc is produced by a script from a
   tool log/report and stored in `results/summary.json` with its source report path. If a tool fails,
   report the failure; never estimate.
2. **Never rewrite or backdate git history.** No force-push to `main`. Work on branch `rework/alu-ppa`.
3. **Commits.**
   - Commit after every completed gate in PROGRESS.md, using Conventional Commits
     (`feat:` `fix:` `test:` `docs:` `build:` `ci:`).
   - The body covers what changed, why, and how it was verified (command + result).
   - Keep the `Co-Authored-By: Claude` trailer.
   - Push the branch after each commit.
   - At the end of each phase, open a PR to `main` with `gh pr create` (summary, verification evidence,
     open issues).
   - **Never merge PRs; the user merges.**
4. **Ask first before:**
   - renaming the repo;
   - changing visibility;
   - archiving or deleting any repo (including `STA`);
   - installing system packages;
   - any action outside this repo.
5. **If a spec item is infeasible** with the installed tools: stop, explain, and propose the closest
   honest alternative. Never silently downgrade.
6. **`PROGRESS.md` is the single source of truth for status.** Update it before every commit.
7. **Explain as you go.**
   - Every design decision gets a `docs/DECISIONS.md` entry (context → options → choice → evidence).
   - Maintain `docs/LEARNING.md` (concepts, explained simply, with code references).
   - Maintain `docs/INTERVIEW.md` (30+ questions, answered with this project's actual numbers).
8. **If you think Part A of the brief is wrong,** say so and wait for the user's answer.

## Layout
```
rtl/        SystemVerilog RTL (alu_pkg.sv, alu_top.sv, adders/*.sv, shifter.sv, clz.sv, cpop.sv)
model/      Python golden model (alu_ref.py) + its unit tests
tb/         cocotb testbenches + coverage
formal/     SymbiYosys .sby jobs (adder miters, ALU equivalence, latency protocol)
flow/       LibreLane config templates
scripts/    env_check, sweep, report parsers, plots, README table generator
results/    machine-generated outputs (summary.json, plots, env_check.txt, ...)
docs/       BRIEF (binding spec), AUDIT, SPEC, MICROARCH, PPA_REPORT, STA_REPORT, DECISIONS, LEARNING, INTERVIEW
legacy/     original alu32_final.v + config.json (kept for history; not reused) + audit probe tb
.github/workflows/  CI: lint, reduced sim, formal (not the full flow)
```
Never commit `runs/`, `sim_build/`, `*.vcd` or `.venv/`.

## Environment
All EDA tools run in the Docker container `iic-osic` (image `hpretl/iic-osic-tools:latest`,
PDK sky130A, std cells `sky130_fd_sc_hd`). The host's `~/projects` is mounted at `/foss/projects`, so this
repo is `/foss/projects/32bit-RTL-To-GDS` inside the container.

Create the container (once; see also `~/vlsi/CLAUDE.md`):
```bash
docker run -d --name iic-osic --user "$(id -u):$(id -g)" --security-opt seccomp=unconfined \
  -e IIC_OSIC_TOOLS_QUIET=1 -e PDK=sky130A \
  -v "$HOME/vlsi":/foss/designs:rw -v "$HOME/projects":/foss/projects:rw \
  hpretl/iic-osic-tools:latest --skip sleep infinity
docker start iic-osic   # after reboot
```

Run anything, headless, from the repo root. **`bash -lc` is required**: without a login shell, PATH and
PDK variables are not set.
```bash
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc '<command>'
```

Python venv (inside the container only; created with `--system-site-packages` so it reuses the image's
cocotb 2.0.1). It adds `cocotb-coverage==2.0`:
```bash
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc \
  'python3 -m venv --system-site-packages .venv && .venv/bin/pip install cocotb-coverage==2.0'
# use: .venv/bin/python ...
```

Make targets. `make` exists only in the container, not on the host:
```bash
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make env'           # tool table -> results/env_check.txt
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make model'         # pytest + Spike cross-check
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make rtl'           # opcodes + lint + synth-check + adder smoke
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make verify'        # lint + model + sim (~35 min) + formal (~4 min) + summary
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make sim-ci formal-ci'  # what CI runs (minutes)
docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make legacy-probe'  # audit evidence
```
- `make model` writes `results/model_test.txt` and `results/model_xcheck.json`.
- The Spike cross-check builds a bare-metal rv32i_zbb program (`model/spike/`) with
  `riscv64-unknown-elf-gcc` and runs it with `spike --isa=rv32i_zbb`.

Verification (Phase 3):
- cocotb TB is `tb/alu_tb.py` (scoreboard, exact-latency check), with coverage in `tb/alu_coverage.py`.
  Run it with `.venv/bin/python scripts/run_sim.py --sim verilator|icarus --adder NAME|all --pipe 0|1
  --vectors N --seed S`.
- Formal: `formal/*.sby` via `python3 scripts/run_formal.py [--quick]`. Use immediate asserts plus
  shadow pipelines (D-017).
- Never mutate `rtl/` while a regression or SBY run is in progress: SBY copies sources when each task
  starts. Mutation checks use copies under `sim_build/`.
- `results/verify_summary.json` is the roll-up; `scripts/verify_summary.py` only reads result files.

RTL conventions (Phase 2, D-012):
- SV subset accepted by Verilator, slang and Icarus. Yosys is always used through slang (`read_slang`;
  LibreLane `USE_SLANG`), because the built-in frontend rejects `parameter string` and in-module
  `import`.
- `ADDER` is an **integer** (`alu_pkg::ADDER_RCA..ADDER_BEH`), since Icarus can't pass string params to
  children. Names are mapped in `scripts/adders.py`.
- One module per file. Package imports go inside module bodies. No lint waivers so far.
- No logic inside port connections, and no multi-item `case` lists in `alu_top` (Icarus, D-021): decode
  into named wires with `assign`.

Spec conventions fixed in Phase 1 (see docs/SPEC.md and docs/DECISIONS.md):
- Latency 2 (PIPE=0) / 3 (PIPE=1).
- SUB C = no borrow.
- Opcodes 0–26 as in SPEC section 3; codes 27–31 are illegal.

Tool notes:
- The image has **LibreLane** (OpenLane 2 successor), not `openlane`.
- The SMT solver is **yices** (z3 and boolector are absent).
- Yosys has the slang SV frontend (`read_slang`); LibreLane exposes it as `USE_SLANG`.
- OpenSTA supports `read_vcd` and `read_saif`.
- `git push` and `gh` run on the host (gh is in `~/.local/bin`), not in the container.
