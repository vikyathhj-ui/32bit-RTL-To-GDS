# rv32-alu-ppa-explorer: top-level entry points (docs/BRIEF.md, A5 "make all").
#
# Run inside the iic-osic container (all tools live there), from the host:
#   docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make <target>'

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PY    ?= .venv/bin/python

.PHONY: help env model model-test model-xcheck rtl lint synth-check opcodes-check adder-smoke legacy-probe clean

help:
	@echo "make env          tool table -> results/env_check.txt"
	@echo "make model        golden-model unit tests + Spike cross-check"
	@echo "make rtl          all Phase 2 RTL checks (opcodes, lint, synth, adder smoke)"
	@echo "make lint         verilator -Wall, 16 alu_top configs + 8 adders -> results/lint_summary.json"
	@echo "make synth-check  yosys (slang) synth, no latches, 16 configs -> results/synth_check.json"
	@echo "make opcodes-check alu_pkg.sv vs model/alu_ref.py and scripts/adders.py"
	@echo "make adder-smoke  early Icarus smoke test of the 8 adders -> results/adder_smoke.txt"
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

legacy-probe:
	scripts/legacy_probe.sh

clean:
	rm -rf sim_build
