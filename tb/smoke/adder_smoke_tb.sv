// adder_smoke_tb: early smoke check for one adder architecture (Phase 2).
// NOT the Phase 3 verification: that is the formal miter + cocotb. This only
// catches gross wiring/index mistakes before they reach formal.
//   - W = 8:  exhaustive over a, b (8 bits each) and cin -> 131072 vectors
//   - W = 32: 20000 random vectors (fixed seed) plus carry corner cases
// Prints one PASS/FAIL line; $fatal on failure so the exit code is non-zero.
module adder_smoke_tb #(
    parameter int    ARCH = alu_pkg::ADDER_BEH,
    parameter string NAME = "BEH"  // for messages only
);

    logic [7:0]  a8, b8, s8;
    logic        c8, co8;
    logic [31:0] a32, b32, s32;
    logic        c32, co32;
    int unsigned errors = 0;
    int unsigned vectors = 0;
    int unsigned seed = 32'd2026;

    adder #(.ARCH(ARCH), .W(8))  u8  (.a(a8),  .b(b8),  .cin(c8),  .sum(s8),  .cout(co8));
    adder #(.ARCH(ARCH), .W(32)) u32 (.a(a32), .b(b32), .cin(c32), .sum(s32), .cout(co32));

    task automatic check32(input logic [31:0] a, input logic [31:0] b, input logic c);
        logic [32:0] exp;
        a32 = a; b32 = b; c32 = c;
        #1;
        exp = {1'b0, a} + {1'b0, b} + {32'd0, c};
        vectors++;
        if ({co32, s32} !== exp) begin
            errors++;
            if (errors <= 10)
                $display("MISMATCH %s W=32 a=%h b=%h cin=%b got=%h exp=%h", NAME, a, b, c, {co32, s32}, exp);
        end
    endtask

    initial begin
        logic [8:0] exp8;
        for (int a = 0; a < 256; a++) begin
            for (int b = 0; b < 256; b++) begin
                for (int c = 0; c < 2; c++) begin
                    a8 = a[7:0]; b8 = b[7:0]; c8 = c[0];
                    #1;
                    exp8 = {1'b0, a8} + {1'b0, b8} + {8'd0, c8};
                    vectors++;
                    if ({co8, s8} !== exp8) begin
                        errors++;
                        if (errors <= 10)
                            $display("MISMATCH %s W=8 a=%h b=%h cin=%b got=%h exp=%h", NAME, a8, b8, c8, {co8, s8}, exp8);
                    end
                end
            end
        end
        // 32-bit carry corner cases: full propagate chains, all generate, alternating.
        check32(32'hFFFFFFFF, 32'h00000000, 1'b1);
        check32(32'hFFFFFFFF, 32'h00000001, 1'b0);
        check32(32'hFFFFFFFF, 32'hFFFFFFFF, 1'b1);
        check32(32'h80000000, 32'h80000000, 1'b0);
        check32(32'hAAAAAAAA, 32'h55555555, 1'b1);
        check32(32'h7FFFFFFF, 32'h00000001, 1'b0);
        for (int i = 0; i < 20000; i++) begin
            check32($urandom(seed), $urandom(seed), 1'($urandom(seed)));
        end
        $display("adder_smoke %-4s %s vectors=%0d errors=%0d", NAME, (errors == 0) ? "PASS" : "FAIL", vectors, errors);
        if (errors != 0) $fatal(1, "adder_smoke: %s failed", NAME);
        $finish;
    end
endmodule
