# rv32-alu-ppa-explorer: top-level entry points (docs/BRIEF.md, A5 "make all").
#
# Run inside the iic-osic container (all tools live there), from the host:
#   docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'make <target>'

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PY    ?= .venv/bin/python

.PHONY: help env model model-test model-xcheck legacy-probe clean

help:
	@echo "make env          tool table -> results/env_check.txt"
	@echo "make model        golden-model unit tests + Spike cross-check"
	@echo "make legacy-probe audit evidence for docs/AUDIT.md"
	@echo "make clean        remove sim_build/"

env:
	scripts/env_check.sh | tee results/env_check.txt

model: model-test model-xcheck

model-test:
	$(PY) -m pytest -p no:cacheprovider | tee results/model_test.txt

model-xcheck:
	$(PY) model/spike_xcheck.py

legacy-probe:
	scripts/legacy_probe.sh

clean:
	rm -rf sim_build
