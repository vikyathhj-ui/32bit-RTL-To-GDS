# prefix-adder-alu-sky130: top-level entry points (docs/BRIEF.md, A5 "make all").
#
# Run inside the iic-osic container (all tools live there), from the host:
#   docker exec -w /foss/projects/<clone folder> iic-osic bash -lc 'make <target>'

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PY    ?= .venv/bin/python

.PHONY: help env model model-test model-xcheck rtl lint synth-check opcodes-check adder-smoke \
        sim sim-ci formal formal-ci verify verify-summary \
        flow-sweep flow-sweep-preserved flow-pipe1 abc-exp power wire-delay signoff summary sta plots \
        readme readme-check bullets reports all legacy-probe clean

help:
	@echo "make all          everything: verify -> flow sweeps -> power -> signoff -> reports"
	@echo "make env          tool table -> results/env_check.txt"
	@echo "make model        golden-model unit tests + Spike cross-check"
	@echo "make rtl          all Phase 2 RTL checks (opcodes, lint, synth, adder smoke)"
	@echo "make lint         verilator -Wall, 16 alu_top configs + 8 adders -> results/lint_summary.json"
	@echo "make synth-check  yosys (slang) synth, no latches, 16 configs -> results/synth_check.json"
	@echo "make opcodes-check alu_pkg.sv vs model/alu_ref.py and scripts/adders.py"
	@echo "make adder-smoke  early Icarus smoke test of the 8 adders -> results/adder_smoke.txt"
	@echo "make sim          full cocotb regression (D-019 budget) -> results/sim/, results/coverage/"
	@echo "make sim-ci       reduced cocotb regression for CI"
	@echo "make formal       all SymbiYosys proofs -> results/formal/summary.json"
	@echo "make formal-ci    CI subset of the proofs"
	@echo "make verify       lint + model + sim + formal + results/verify_summary.json"
	@echo "make flow-sweep   LibreLane min-period sweep, default flow (hours) -> results/flow/sweep/"
	@echo "make flow-sweep-preserved  same with structure-preserved synthesis (D-027)"
	@echo "make abc-exp      ABC structure experiment -> results/flow/abc_experiment.json"
	@echo "make power        gate-level workload power on each closing run"
	@echo "make wire-delay   wire share of each closing run's critical path (D-024)"
	@echo "make flow-pipe1   PIPE=1 sweep of HC preserved, the STA fix (D-032)"
	@echo "make signoff      DRC/LVS/antenna/IR(VCD)/render evidence for the recommended config (D-031)"
	@echo "make summary      build results/summary.json from all of the above"
	@echo "make sta          per-corner critical paths -> results/sta/"
	@echo "make plots        Pareto plots -> results/plots/"
	@echo "make readme       README table from summary.json (readme-check: fail if stale)"
	@echo "make bullets      results/resume_bullets.md from summary.json"
	@echo "make legacy-probe audit evidence for docs/AUDIT.md"
	@echo "make clean        remove sim_build/"

env:
	scripts/env_check.sh | tee results/env_check.txt

model: model-test model-xcheck

model-test:
	$(PY) -m pytest -p no:cacheprovider | tee results/model_test.txt

model-xcheck:
	$(PY) model/spike_xcheck.py

rtl: opcodes-check lint synth-check adder-smoke

lint:
	python3 scripts/lint.py

synth-check:
	python3 scripts/synth_check.py

opcodes-check:
	python3 scripts/check_opcodes.py

adder-smoke:
	scripts/adder_smoke.sh

# Vector budget (DECISIONS D-019): >= 1e6 random per adder on Verilator (PIPE=0),
# 1e5 per adder with PIPE=1, and 2e4 per adder on Icarus to show both simulators agree.
SIM_VECTORS      ?= 1000000
SIM_VECTORS_PIPE ?= 100000
SIM_VECTORS_IVL  ?= 20000

sim:
	$(PY) scripts/run_sim.py --sim verilator --adder all --pipe 0 --vectors $(SIM_VECTORS)
	$(PY) scripts/run_sim.py --sim verilator --adder all --pipe 1 --vectors $(SIM_VECTORS_PIPE)
	$(PY) scripts/run_sim.py --sim icarus    --adder all --pipe 0 --vectors $(SIM_VECTORS_IVL)

sim-ci:
	for a in BEH KS RCA; do $(PY) scripts/run_sim.py --sim verilator --adder $$a --vectors 20000 || exit 1; done
	$(PY) scripts/run_sim.py --sim verilator --adder BEH --pipe 1 --vectors 20000
	$(PY) scripts/run_sim.py --sim icarus    --adder BEH --vectors 5000

formal:
	python3 scripts/run_formal.py

formal-ci:
	python3 scripts/run_formal.py --quick

verify-summary:
	python3 scripts/verify_summary.py

verify: lint model sim formal verify-summary

# Seeds are the ones the committed sweeps used, so finished runs in runs/ are reused, not re-run.
flow-sweep:
	python3 scripts/sweep.py --seed 20 --jobs 3

flow-sweep-preserved:
	python3 scripts/sweep.py --variant preserved --seed 12 --jobs 2

flow-pipe1:
	python3 scripts/sweep.py --variant preserved --pipe 1 --adder HC --seed 12 --jobs 1

abc-exp:
	python3 scripts/abc_exp.py

power:
	$(PY) scripts/power_all.py

wire-delay:
	python3 scripts/wire_delay.py

signoff:
	python3 scripts/signoff.py --arch HC --variant preserved

summary:
	python3 scripts/parse_flow.py

sta:
	python3 scripts/sta_report.py

plots:
	python3 scripts/plots.py

readme:
	python3 scripts/gen_readme_table.py

readme-check:
	python3 scripts/gen_readme_table.py --check

bullets:
	python3 scripts/resume_bullets.py

reports: summary sta plots readme bullets

# BRIEF A5 "make all": lint -> sim -> formal -> flow sweep -> reports. With runs/ present every
# finished LibreLane run is reused; from scratch the sweeps take many hours.
all: verify flow-sweep flow-sweep-preserved flow-pipe1 abc-exp power wire-delay signoff reports

legacy-probe:
	scripts/legacy_probe.sh

clean:
	rm -rf sim_build
