# rv32-alu-ppa-explorer *(rework in progress)*

This repository is being reworked into an RV32I + Zbb ALU with an adder-architecture design-space
exploration (RCA, CLA4, CSLA, Brent–Kung, Kogge–Stone, Sklansky, Han–Carlson, behavioural). Each
architecture is verified with cocotb and SymbiYosys and taken RTL-to-GDS on SKY130 with LibreLane.

- Spec and plan: [`docs/BRIEF.md`](docs/BRIEF.md)
- Status: [`PROGRESS.md`](PROGRESS.md)
- What was wrong with the original design: [`docs/AUDIT.md`](docs/AUDIT.md)
- Original files: [`legacy/`](legacy/)

No results are published yet. All numbers will be generated from `results/summary.json`.
