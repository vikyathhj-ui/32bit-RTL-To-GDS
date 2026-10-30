# PROGRESS

Single source of truth for status. Update this before every commit.
Spec: `docs/BRIEF.md`. Branch: `rework/alu-ppa`.

**Current state:** Phases 0–2 merged (PR #1 `044d4ca`, PR #2 `dc2a1dc`). Phase 3 complete, CI green, PR #3 open (awaiting owner merge). Next: Phase 4 (physical design sweep). Plan it first.

## Phase 0 — Setup and audit
- [x] Environment check script (`scripts/env_check.sh` → `results/env_check.txt`). All tools found after
      adding `cocotb-coverage==2.0` to the repo venv.
- [x] Audit of legacy repo + STA repo → `docs/AUDIT.md`. Bugs confirmed by `scripts/legacy_probe.sh` →
      `results/legacy_probe.txt`.
- [x] Repo files: `docs/BRIEF.md` (verbatim), `CLAUDE.md`, `PROGRESS.md`, `.gitattributes`, `.gitignore`,
      `LICENSE` (MIT).
- [x] Layout created; legacy RTL moved to `legacy/` via `git mv`.
- [x] Commit + push `rework/alu-ppa`.
- [x] PR for Phase 0 (opened together with Phase 1's PR, as agreed in the Phase 0 plan).

## Phase 1 — Spec and golden model
- [x] `docs/SPEC.md`: functional spec, op table with bit-exact definitions, interface timing diagram
      (WaveDrom).
- [x] Spec clarifications agreed with the owner: latency 2/3 (D-006), Zbb vectors = spec-derived + Spike
      (D-007), SUB C = no borrow (D-008).
- [x] `model/alu_ref.py`: bit-exact model of all 27 ops + flags + `illegal_op`.
- [x] Model unit tests (`model/test_alu_ref.py`): hand vectors, flags, illegal ops, strlen/strcmp
      idioms, properties → `results/model_test.txt`.
- [x] Spike cross-check (`model/spike_xcheck.py`) → `results/model_xcheck.json` (PASS); mutation check
      confirmed it detects errors.
- [x] `Makefile`: `make env`, `make model` (run inside the container).
- [x] **Gate:** model tests pass (`make model`). Commit, push, open PR.

## Phase 2 — RTL
- [x] Check Yosys SV support (slang vs. built-in frontend); decide on the language subset (D-012). Yosys
      is used via slang. `ADDER` is an integer code because Icarus can't pass string params.
- [x] Check that the `rtl/alu_pkg.sv` opcodes (and adder codes) match the model and `scripts/adders.py`
      (`make opcodes-check`).
- [x] `rtl/alu_pkg.sv` (opcodes, adder codes).
- [x] `rtl/adders/*.sv`, common interface: RCA, CLA4, CSLA, BK, KS, SK, HC, BEH (prefix adders use explicit
      `pg_black`/`pg_gray` cells in `generate` loops).
- [x] `rtl/shifter.sv` (63→32 funnel, left via bit reversal), `rtl/clz.sv` + `clz_tree.sv` (log-depth
      tree, CTZ via reversal), `rtl/cpop.sv` (adder tree).
- [x] `rtl/alu_top.sv`: registered I/O, `PIPE` parameter, shared adder/shifter/inverter, `illegal_op`.
- [x] Early adder smoke test (`make adder-smoke`): 8/8 PASS. Found and fixed bug B-001 (CLA4 cout).
- [x] `make synth-check`: Yosys (slang) synthesis, 16/16 configs, no latches.
- [x] **Gate:** `verilator --lint-only -Wall` clean for all 8 `ADDER` values × PIPE 0/1, plus each adder
      alone: 24/24, 0 waivers (`make lint` → `results/lint_summary.json`). Commit done.
- [x] Pushed; PR #2 opened after PR #1 was merged.

## Phase 3 — Verification
- [x] cocotb directed tests (corners, shift amounts 0/1/31/32/33, op × flag edges, illegal opcodes,
      back-to-back, bubbles, reset), on Icarus and Verilator (`tb/alu_tb.py`).
- [x] ≥10⁶ constrained-random vectors per adder config (Verilator), self-checking against
      `model/alu_ref.py`: exactly 1,000,000 checked per config (`results/sim/verilator_*_PIPE0.json`);
      also PIPE=1 (100k) and Icarus (20k).
- [x] Functional coverage (cocotb-coverage): 100% of the 495 defined bins in every run; left-out bins
      justified in `docs/COVERAGE.md`.
- [x] Formal: per-adder equivalence miter: 8/8 PASS.
- [x] Formal: full-ALU equivalence vs `formal/alu_ref_beh.sv`: 16/16 PASS (ADDER × PIPE).
- [x] Formal: `out_valid` latency protocol: 2/2 PASS (PIPE 0/1).
- [x] `make verify` → `results/verify_summary.json` (PASS).
- [x] Bugs found by verification recorded in `docs/DECISIONS.md`: none functional in Phase 3; Icarus
      issue D-021; bench vector-count fix.
- [x] `.github/workflows/ci.yml`: lint, model, reduced sim, formal subset (OSS CAD Suite, D-020).
- [x] **Gate:** 8/8 configs pass, coverage closed, all proofs PASS. Committed locally.
- [x] Pushed after PR #2 was merged. CI green on run 41067482198 (after fixing a Verilator 5.053
      SIMILARNAME lint warning). PR #3 opened.

## Phase 4 — Physical design sweep
- [ ] `flow/` config template; fixed die/utilisation policy (DECISIONS.md).
- [ ] `scripts/sweep.py`: min closing period at the slowest corner, 0.25 ns resolution (plus a
      monotonicity check).
- [ ] Report parser → `results/summary.json` (area, cells, util, WNS/TNS setup+hold per corner, fmax per
      corner, critical path, logic depth).
- [ ] Workload VCD (50% add/sub, 20% logic, 20% shift, 10% Zbb) → OpenSTA activity-annotated power;
      energy/op.
- [ ] ABC structure experiment: default vs. structure-preserving.
- [ ] Post-synth vs. post-route delay per architecture.
- [ ] **Gate:** all 8 configs complete, `summary.json` populated. Commit, push, open PR.

## Phase 5 — Signoff, reports, docs
- [ ] Recommended config chosen from data (DECISIONS.md).
- [ ] Signoff: Magic + KLayout DRC, Netgen LVS, antenna clean; IR-drop report; GDS render PNG.
- [ ] `scripts/plots.py` → `results/plots/` (fmax vs. area, energy/op vs. delay, area vs. architecture).
- [ ] `docs/MICROARCH.md`, `docs/PPA_REPORT.md`, `docs/STA_REPORT.md`.
- [ ] `README.md` with table auto-generated by `scripts/gen_readme_table.py`.
- [ ] Final `docs/LEARNING.md` and `docs/INTERVIEW.md` (30+ questions, required topics covered).
- [ ] `results/resume_bullets.md` (3 bullets, numbers only from summary.json).
- [ ] `make all` (lint → sim → formal → sweep → reports).
- [ ] Final PR opened.
- [ ] Ask the user about renaming the repo to `rv32-alu-ppa-explorer` and archiving `STA`.

## Open issues
- The host has no `make`; run `make` inside the container (see CLAUDE.md). Installing it on the host
  would need sudo, which is the owner's call.
- CI uses OSS CAD Suite (pinned 2026-10-14), not the iic-osic image, so tool versions differ (D-020).
  `test_spike_xcheck` skips there with a reason.
- CI's newer Verilator found a lint issue the container's version did not (D-020). Re-check CI after
  RTL changes, not just the local `make lint`.
