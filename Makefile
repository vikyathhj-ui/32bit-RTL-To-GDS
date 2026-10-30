# rv32-alu-ppa-explorer: top-level entry points (docs/BRIEF.md, A5 "make all").
#
# Run inside the iic-osic container (all tools live there), from the host:
#   docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make <target>'

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PY    ?= .venv/bin/python

.PHONY: help env model model-test model-xcheck rtl lint synth-check opcodes-check adder-smoke \
        sim sim-ci formal formal-ci verify verify-summary \
        flow-sweep flow-sweep-preserved abc-exp power summary legacy-probe clean

help:
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
	@echo "make summary      build results/summary.json from all of the above"
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

flow-sweep:
	python3 scripts/sweep.py --jobs 3

flow-sweep-preserved:
	python3 scripts/sweep.py --variant preserved --seed 12 --jobs 2

abc-exp:
	python3 scripts/abc_exp.py

power:
	$(PY) scripts/power_all.py

summary:
	python3 scripts/parse_flow.py

legacy-probe:
	scripts/legacy_probe.sh

clean:
	rm -rf sim_build
