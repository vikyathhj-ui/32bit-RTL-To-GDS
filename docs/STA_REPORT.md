# STA report — HC, structure-preserved flow

This report replaces the old `STA` repository. It covers the recommended configuration (D-031): the
Han–Carlson adder, structure-preserved flow, PIPE=0, at its minimum closing period. It also covers
the one fix attempted, PIPE=1 (D-032).

- **Source:** the post-route STA of each closing run, LibreLane's `OpenROAD.STAPostPNR` step (OpenSTA,
  extracted SPEF for min/nom/max RC, the flow's SDC: 20% input/output delay, 0.25 ns clock
  uncertainty, 5% timing derate, propagated clock).
- `scripts/sta_report.py` takes the worst setup and hold path at each of the 9 corners and writes
  `results/sta/<config>.json`. The worst-path excerpt of each report is saved alongside it as
  `results/sta/<config>/<corner>.{setup,hold}.rpt`. Every table below is printed by
  `python3 scripts/sta_report.py --md`.
- **Path split:**
  - *logic* = combinational cells other than buffers;
  - *delay cells* = `clkdlybuf*`/`dlygate*`;
  - *buffers* = `buf_*`/`clkbuf_*`;
  - *clk→Q* = the launch flop.
  - The remainder is wire RC between pins, under 0.05 ns on every path. A wire's capacitance shows
    up in its *driver's* delay; D-024 measures that effect separately.

## 1. The recommended configuration, PIPE=0

**HC_preserved** — T = 15.75 ns, PIPE=0, latency 2 cycles

| Corner | Setup WS (ns) | Setup TNS | fmax (MHz) | Worst setup path | Logic cells | Data path (ns) | Logic / delay cells / buffers / clk→Q (ns) | Hold WS (ns) | Worst hold path |
|---|---|---|---|---|---|---|---|---|---|
| max_ss_100C_1v60 | 0.2019 | 0 | 64.32 | `b0[4]` → `_0000_` | 12 | 14.923 | 8.34 / 5.68 / 0.00 / 0.89 | 1.2195 | `b0[16]` → `y_next[16]` |
| nom_ss_100C_1v60 | 0.5246 | 0 | 65.68 | `b0[4]` → `_0000_` | 12 | 14.601 | 8.18 / 5.53 / 0.00 / 0.88 | 1.2044 | `b0[16]` → `y_next[16]` |
| min_ss_100C_1v60 | 0.8487 | 0 | 67.11 | `b0[4]` → `_0000_` | 12 | 14.274 | 8.02 / 5.37 / 0.00 / 0.88 | 1.1896 | `b0[16]` → `y_next[16]` |
| max_tt_025C_1v80 | 7.4272 | 0 | 120.15 | `u_cpop.g_node.u_lo.g_node.u_lo.g_node.u_lo.g_node.u_lo.g_node.ch` → `_0000_` | 16 | 7.905 | 4.72 / 2.61 / 0.17 / 0.36 | 0.4953 | `b0[16]` → `y_next[16]` |
| nom_tt_025C_1v80 | 7.6157 | 0 | 122.94 | `u_cpop.g_node.u_lo.g_node.u_lo.g_node.u_lo.g_node.u_lo.g_node.ch` → `_0000_` | 16 | 7.715 | 4.63 / 2.54 / 0.17 / 0.36 | 0.4856 | `b0[16]` → `y_next[16]` |
| min_tt_025C_1v80 | 7.7953 | 0 | 125.71 | `u_cpop.g_node.u_lo.g_node.u_lo.g_node.u_lo.g_node.u_lo.g_node.ch` → `_0000_` | 16 | 7.534 | 4.54 / 2.46 / 0.17 / 0.35 | 0.4760 | `b0[16]` → `y_next[16]` |
| max_ff_n40C_1v95 | 9.5536 | 0 | 161.38 | `in_valid` → `net417` | 0 | 3.096 | 0.00 / 2.80 / 0.27 / 0.00 | 0.2199 | `b0[16]` → `y_next[16]` |
| nom_ff_n40C_1v95 | 9.6004 | 0 | 162.61 | `in_valid` → `net417` | 0 | 3.037 | 0.00 / 2.75 / 0.27 / 0.00 | 0.2135 | `b0[16]` → `y_next[16]` |
| min_ff_n40C_1v95 | 9.6486 | 0 | 163.9 | `in_valid` → `net417` | 0 | 2.978 | 0.00 / 2.71 / 0.26 / 0.00 | 0.2068 | `b0[16]` → `y_next[16]` |

Cells on the worst `max_ss_100C_1v60` setup path (results/sta/HC_preserved/max_ss_100C_1v60.setup.rpt):

| # | Instance | Cell | Fan-out | Delay (ns) |
|---|---|---|---|---|
| 1 | fanout337 | clkdlybuf4s50_1 | 6 | 1.249 |
| 2 | fanout335 | clkdlybuf4s15_2 | 10 | 0.836 |
| 3 | _1255_ | inv_1 | 1 | 0.203 |
| 4 | fanout308 | clkdlybuf4s50_1 | 8 | 1.341 |
| 5 | fanout307 | clkdlybuf4s15_2 | 10 | 0.897 |
| 6 | _1524_ | o21ai_0 | 2 | 0.585 |
| 7 | fanout206 | clkdlybuf4s50_1 | 10 | 1.354 |
| 8 | _1612_ | o22ai_1 | 3 | 0.908 |
| 9 | _1900_ | mux2i_1 | 3 | 0.512 |
| 10 | _2037_ | mux4_2 | 2 | 1.196 |
| 11 | _2038_ | mux2_1 | 2 | 0.800 |
| 12 | _2046_ | o21ai_0 | 1 | 0.277 |
| 13 | _2062_ | o21ai_0 | 2 | 0.340 |
| 14 | _2572_ | or4_4 | 1 | 1.179 |
| 15 | _2574_ | or4b_4 | 1 | 1.007 |
| 16 | _2575_ | or4_4 | 1 | 0.937 |
| 17 | _2579_ | nor4b_2 | 1 | 0.392 |

### What limits the clock

- **Slow corners (ss, 100 °C, 1.60 V): the shifter, not the adder.** The path starts at operand
  register `b0[4]`, the shift amount's 16-position bit. It runs through two levels of fanout buffers
  (b[4] steers every mux of the shifter's first stage), the shifter's mux stages (`mux2i`, `mux4`,
  `mux2`), the 3:1 result mux into `y_next[6]`, then a four-level OR tree (`or4`, `or4b`, `or4`,
  `nor4b`). It ends at `_0000_`, the D input of the **Z flag** register (`flags[2]`).
- **Typical corners (tt, 25 °C, 1.80 V): the adder and the same flag logic.** The path starts at an
  operand flop (its Q net carries a name from the CPOP hierarchy, because the net is shared). It runs
  through the Han–Carlson prefix tree (`g_l0` → `g_lvl[2]` → `g_lvl[3]` → `g_lvl[4]` → `g_fix`), the
  compare select and the result mux, then the same OR tree into the Z flag.
  - Two different paths are worst at different corners because their delays are close. Shifter muxes
    and buffers slow down more at ss than the adder's AOI cells do.
- **The common element is the zero flag:** Z = NOR of all 32 result bits, computed *after* the result
  mux, so it sits at the end of every unit's path.
- **Fast corners (ff, −40 °C, 1.95 V):** the worst setup path is the input port `in_valid` (20%
  input delay) through its fanout tree into the flops' enable pins. It has more than 9.5 ns of slack.
  Setup is never a problem at ff.
- **Delay cells used as buffers:** 5.68 ns of the 14.92 ns data path at `max_ss` is spent in
  `clkdlybuf4s50_1`/`clkdlybuf4s15_2` cells. In the whole netlist, 182 of the 237 `fanout*` buffers
  that OpenROAD's repair inserted are these delay cells.
  - LibreLane's sky130 configuration excludes them from synthesis (`synth_excluded.cells`) but not
    from PnR (`pnr_excluded.cells`), so the resizer may use them for fan-out repair. They are slow,
    by design.
  - This was **not** attempted as a fix (owner's decision, D-032). It is the obvious next experiment:
    `EXTRA_EXCLUDED_CELLS: ["sky130_fd_sc_hd__clkdlybuf*", "sky130_fd_sc_hd__dlygate*"]`.

### Setup vs hold across corners
- **Setup** is limited at `max_ss_100C_1v60`: slow transistors (ss), high temperature, low voltage and
  maximum wire RC all make data late. fmax spans 64.32 MHz there to 163.9 MHz at `min_ff_n40C_1v95`.
- **Hold** is limited at the ff corners (worst 0.2068 ns at `min_ff_n40C_1v95`): fast cells make new
  data arrive soon after the clock edge. At ss the hold slack is about 1.2 ns. The worst hold path
  is a short operand-to-result-register path (`b0[16]` → `y_next[16]`).
- Every corner has setup TNS = 0 and hold WS > 0, so the design closes everywhere at 15.75 ns.

## 2. Fix attempted: PIPE=1 (D-032)

`PIPE=1` (D-013) registers each unit's final result (`r_add`, `r_shift`, `r_misc`, plus select and
flags) before the result mux and flag logic. The same sweep found the new minimum period.

**HC_preserved_P1** — T = 11.5 ns, PIPE=1, latency 3 cycles

| Corner | Setup WS (ns) | Setup TNS | fmax (MHz) | Worst setup path | Logic cells | Data path (ns) | Logic / delay cells / buffers / clk→Q (ns) | Hold WS (ns) | Worst hold path |
|---|---|---|---|---|---|---|---|---|---|
| max_ss_100C_1v60 | 0.0811 | 0 | 87.57 | `op0[1]` → `r_add[26]` | 17 | 10.341 | 7.34 / 0.72 / 1.30 / 0.94 | 0.4157 | `rst_n` → `net71` |
| nom_ss_100C_1v60 | 0.3523 | 0 | 89.7 | `op0[1]` → `r_add[22]` | 17 | 10.027 | 7.02 / 0.00 / 2.05 / 0.94 | 0.4497 | `rst_n` → `net71` |
| min_ss_100C_1v60 | 0.6189 | 0 | 91.9 | `op0[1]` → `r_add[22]` | 18 | 9.790 | 6.83 / 0.00 / 2.01 / 0.93 | 0.4796 | `rst_n` → `net71` |
| max_tt_025C_1v80 | 5.3357 | 0 | 162.23 | `op0[4]` → `r_add[20]` | 17 | 5.561 | 3.67 / 0.00 / 1.50 / 0.35 | 0.3714 | `r_add2[14]` → `y_next[14]` |
| nom_tt_025C_1v80 | 5.4690 | 0 | 165.81 | `op0[4]` → `r_add[20]` | 17 | 5.434 | 3.60 / 0.00 / 1.47 / 0.35 | 0.3691 | `r_add2[14]` → `y_next[14]` |
| min_tt_025C_1v80 | 5.5707 | 0 | 168.65 | `in_valid` → `net356` | 0 | 3.639 | 0.00 / 3.35 / 0.28 / 0.00 | 0.3680 | `r_add2[14]` → `y_next[14]` |
| max_ff_n40C_1v95 | 6.6906 | 0 | 207.93 | `in_valid` → `net356` | 0 | 2.589 | 0.00 / 2.35 / 0.22 / 0.00 | 0.1161 | `r_misc2[13]` → `y_next[13]` |
| nom_ff_n40C_1v95 | 6.7229 | 0 | 209.33 | `in_valid` → `net356` | 0 | 2.542 | 0.00 / 2.32 / 0.21 / 0.00 | 0.1136 | `r_misc2[13]` → `y_next[13]` |
| min_ff_n40C_1v95 | 6.7649 | 0 | 211.19 | `in_valid` → `net356` | 0 | 2.487 | 0.00 / 2.28 / 0.20 / 0.00 | 0.1110 | `r_misc2[13]` → `y_next[13]` |

Cells on the worst `max_ss_100C_1v60` setup path (results/sta/HC_preserved_P1/max_ss_100C_1v60.setup.rpt):

| # | Instance | Cell | Fan-out | Delay (ns) |
|---|---|---|---|---|
| 1 | fanout232 | buf_6 | 3 | 0.279 |
| 2 | _1235_ | nor3b_1 | 3 | 0.361 |
| 3 | fanout224 | buf_4 | 5 | 0.335 |
| 4 | _1236_ | and2_4 | 5 | 0.349 |
| 5 | _1247_ | nor4_4 | 2 | 0.559 |
| 6 | _1251_ | nand2_2 | 2 | 0.274 |
| 7 | _1254_ | a211oi_4 | 3 | 0.781 |
| 8 | fanout143 | buf_6 | 3 | 0.425 |
| 9 | rebuffer363 | buf_4 | 2 | 0.265 |
| 10 | _1259_ | xnor2_1 | 2 | 0.221 |
| 11 | _1260_ | nand2_2 | 4 | 0.242 |
| 12 | _1261_ | inv_1 | 4 | 0.226 |
| 13 | _1264_ | nor2_1 | 3 | 0.459 |
| 14 | u_adder.g_hc.u_add.g_l0[31].g_black.u_cell/_1_ | and2_0 | 2 | 0.570 |
| 15 | u_adder.g_hc.u_add.g_lvl[1].g_bit[31].g_black.u_cell/_1_ | and2_0 | 2 | 0.459 |
| 16 | u_adder.g_hc.u_add.g_lvl[2].g_bit[31].g_black.u_cell/_1_ | and2_0 | 2 | 0.384 |
| 17 | u_adder.g_hc.u_add.g_lvl[3].g_bit[31].g_black.u_cell/_1_ | and2_0 | 1 | 0.353 |
| 18 | u_adder.g_hc.u_add.g_lvl[4].g_bit[31].g_gray.u_cell/_0_ | a21o_4 | 6 | 0.431 |
| 19 | _1283_ | a21oi_1 | 2 | 0.255 |
| 20 | fanout110 | clkdlybuf4s15_2 | 10 | 0.721 |
| 21 | _1583_ | a221oi_1 | 1 | 0.577 |
| 22 | _1584_ | o211ai_1 | 1 | 0.838 |

### Effect

| | PIPE=0 | PIPE=1 |
|---|---|---|
| Min period (ns) | 15.75 | 11.5 |
| fmax at `max_ss_100C_1v60` (MHz) | 64.32 | 87.57 |
| Critical path at `max_ss` | `b0[4]` → shifter → result mux → Z flag | `op0[1]` → decode → `~b` → HC prefix → compare → `r_add[26]` |
| Delay cells on that path (ns) | 5.68 | 0.72 |
| Standard cells / cell area (µm²) | 2567 / 18,735.5 | 2703 / 20,666.1 |
| Energy per operation (pJ) | 35.56 | 40.65 |
| Latency (cycles × T) | 2 × 15.75 = 31.5 ns | 3 × 11.5 = 34.5 ns |

(Values from `results/summary.json`, `variants.preserved.HC` and `variants.preserved_P1.HC`, and from
the tables above. See D-032.)

- **The fix worked for the reason expected:** with the flag logic in its own stage, the adder is
  finally the critical path, as it should be for an adder study.
- **The cost:** 136 more cells (the pipeline flops and their clock tree), 14% more energy per
  operation, and one more cycle of latency. A single, isolated operation takes 3 ns longer. Throughput
  improves with the clock.
- **Hold at PIPE=1:** worst 0.1110 ns at `min_ff_n40C_1v95` (`r_misc2[13]` → `y_next[13]`). The new
  stage-2 paths are short: a mux and a flop.
- **Verified:** the PIPE=1 post-route netlist passes the 10,000-operation gate-level workload against
  the golden model at latency 3.

## 3. Reading these reports
- **WS** is worst slack (required − arrival). **TNS** is total negative slack, the sum over failing
  endpoints. fmax = 1 / (T − WS).
- **min/nom/max** = the extracted-RC corner: wire resistance and capacitance at their minimum,
  nominal or maximum process values.
- `_0000_`, `_2647_` and similar are synthesis-generated names. The excerpts keep the full cell and
  pin list, so every number here can be traced to an OpenSTA report line.
