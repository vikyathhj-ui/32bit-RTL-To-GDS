read_liberty /foss/pdks/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
read_db /foss/projects/32bit-RTL-To-GDS/runs/HC_P0_T15.75_preserved/runs/HC_P0_T15.75_preserved/final/odb/alu_top.odb
read_sdc /foss/projects/32bit-RTL-To-GDS/runs/HC_P0_T15.75_preserved/runs/HC_P0_T15.75_preserved/final/sdc/alu_top.sdc
read_spef /foss/projects/32bit-RTL-To-GDS/runs/HC_P0_T15.75_preserved/runs/HC_P0_T15.75_preserved/final/spef/nom/alu_top.nom.spef
set_propagated_clock [all_clocks]
read_vcd -scope alu_top /foss/projects/32bit-RTL-To-GDS/sim_build/gls/HC_P0_T15.75_preserved/workload.vcd
report_activity_annotation
report_power -digits 6
set_pdnsim_net_voltage -net VPWR -voltage 1.8
analyze_power_grid -net VPWR -voltage_file /foss/projects/32bit-RTL-To-GDS/results/signoff/HC_preserved/net-VPWR.csv
set_pdnsim_net_voltage -net VGND -voltage 0
analyze_power_grid -net VGND -voltage_file /foss/projects/32bit-RTL-To-GDS/results/signoff/HC_preserved/net-VGND.csv
