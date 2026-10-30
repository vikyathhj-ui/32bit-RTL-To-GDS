#!/usr/bin/env bash
# Early smoke check of all 8 adder architectures with Icarus (tb/smoke/adder_smoke_tb.sv).
# Writes results/adder_smoke.txt; exits non-zero if any architecture fails.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p sim_build/smoke results
out=results/adder_smoke.txt
: > "$out"
rc=0
# name:code pairs from scripts/adders.py (single source for the name -> code map)
for pair in $(python3 -c 'import sys; sys.path.insert(0,"scripts"); from adders import ADDERS; print(" ".join(f"{n}:{c}" for n,c in ADDERS.items()))'); do
    arch=${pair%%:*}; code=${pair##*:}
    if iverilog -g2012 -s adder_smoke_tb -P "adder_smoke_tb.ARCH=$code" -P "adder_smoke_tb.NAME=\"$arch\"" \
            -o "sim_build/smoke/$arch" rtl/alu_pkg.sv rtl/adders/*.sv tb/smoke/adder_smoke_tb.sv \
            > "sim_build/smoke/$arch.compile.log" 2>&1; then
        vvp -n "sim_build/smoke/$arch" | grep -E "adder_smoke|MISMATCH" | tee -a "$out" || rc=1
        grep -q "adder_smoke $arch *PASS" "$out" || rc=1
    else
        echo "adder_smoke $arch COMPILE-FAIL (sim_build/smoke/$arch.compile.log)" | tee -a "$out"
        head -5 "sim_build/smoke/$arch.compile.log"
        rc=1
    fi
done
exit $rc
