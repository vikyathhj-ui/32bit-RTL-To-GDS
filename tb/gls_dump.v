// gls_dump: second top-level module for gate-level power simulation. Dumps every
// net of alu_top to the file named by `GLS_VCD (written as FST by the cocotb
// Icarus runner, converted to VCD by scripts/gls_power.py for OpenSTA, D-025).
module gls_dump;
    initial begin
        $dumpfile(`GLS_VCD);
        $dumpvars(0, alu_top);
    end
endmodule
