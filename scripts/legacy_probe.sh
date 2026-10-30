#!/usr/bin/env bash
# Simulates legacy/alu32_final.v with legacy/tb_probe.v (Icarus) and saves the log
# to results/legacy_probe.txt. Evidence for docs/AUDIT.md.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p sim_build
iverilog -g2012 -o sim_build/legacy_probe legacy/tb_probe.v legacy/alu32_final.v
vvp -n sim_build/legacy_probe | tee results/legacy_probe.txt
