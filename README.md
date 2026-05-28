# 32-bit ALU — RTL to GDS Implementation

A complete RTL-to-GDS flow for an improved 32-bit Arithmetic Logic Unit using
**Verilog → OpenLane → Sky130 PDK → GDSII**

## Results
- ✅ Magic DRC: 0 violations
- ✅ LVS: Clean (2338 nets)
- ✅ No setup violations
- ✅ No hold violations

## ALU Features
- 25 operations (ADD, SUB, AND, OR, XOR, NOR, NAND, NOT, SLL, SRL, SRA, ROL, ROR, SLT, SLTU, SEQ, SNE, SGE, ADDC, SUBB, ABS, MAX, MIN, PASS_A, PASS_B)
- 4 status flags: Zero, Carry, Overflow, Negative
- Clocked pipeline stage (100 MHz target)
- Active-low reset
- valid_in / valid_out handshaking

## Tool Stack
| Tool | Purpose |
|------|---------|
| Verilog | RTL design |
| OpenLane v1.1.1 | RTL-to-GDS automation |
| Sky130A PDK | 130nm open-source process |
| Magic | DRC + LVS |
| KLayout | GDS viewer |

## Flow
RTL → Synthesis → Floorplan → Placement → CTS → Routing → DRC/LVS → GDS

## GDS Layout
Located at: `runs/RUN_IMPROVED/results/final/gds/alu32.gds`
