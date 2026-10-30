// alu_ref_beh: behavioural reference ALU for formal equivalence (BRIEF A3 formal 2).
//
// Written directly from docs/SPEC.md sections 3-5 with plain operators (+, <<,
// >>, >>>, $signed compares, simple loops), NOT from rtl/alu_top.sv: it shares
// no modules and no package with the RTL. Opcodes are the literal numbers from
// the SPEC table so that an encoding error in alu_pkg would also be caught.
module alu_ref_beh (
    input  logic [4:0]  op,
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic [31:0] y,
    output logic [3:0]  flags,  // {N, Z, C, V}
    output logic        illegal
);
    logic [32:0] s;
    logic [4:0]  sh;
    logic        c, v;
    logic [5:0]  cnt;
    logic        found;

    always_comb begin
        s = 33'd0;
        sh = b[4:0];
        c = 1'b0;
        v = 1'b0;
        cnt = 6'd0;
        found = 1'b0;
        illegal = 1'b0;
        y = 32'd0;
        case (op)
            5'd0: begin  // ADD
                s = {1'b0, a} + {1'b0, b};
                y = s[31:0];
                c = s[32];
                v = (a[31] == b[31]) && (y[31] != a[31]);
            end
            5'd1: begin  // SUB: a + ~b + 1; C = carry-out = no borrow (SPEC 4)
                s = {1'b0, a} + {1'b0, ~b} + 33'd1;
                y = s[31:0];
                c = s[32];
                v = (a[31] != b[31]) && (y[31] != a[31]);
            end
            5'd2:  y = a << sh;                                           // SLL
            5'd3:  y = ($signed(a) < $signed(b)) ? 32'd1 : 32'd0;         // SLT
            5'd4:  y = (a < b) ? 32'd1 : 32'd0;                           // SLTU
            5'd5:  y = a ^ b;                                             // XOR
            5'd6:  y = a >> sh;                                           // SRL
            5'd7:  y = $unsigned($signed(a) >>> sh);                      // SRA
            5'd8:  y = a | b;                                             // OR
            5'd9:  y = a & b;                                             // AND
            5'd10: y = ($signed(a) < $signed(b)) ? a : b;                 // MIN
            5'd11: y = ($signed(a) < $signed(b)) ? b : a;                 // MAX
            5'd12: y = (a < b) ? a : b;                                   // MINU
            5'd13: y = (a < b) ? b : a;                                   // MAXU
            5'd14: y = a & ~b;                                            // ANDN
            5'd15: y = a | ~b;                                            // ORN
            5'd16: y = ~(a ^ b);                                          // XNOR
            5'd17: y = (sh == 5'd0) ? a : ((a << sh) | (a >> (6'd32 - {1'b0, sh})));  // ROL
            5'd18: y = (sh == 5'd0) ? a : ((a >> sh) | (a << (6'd32 - {1'b0, sh})));  // ROR
            5'd19: begin  // CLZ: zeros above the highest 1, 32 for 0
                for (int i = 31; i >= 0; i--) begin
                    if (!found && a[i]) found = 1'b1;
                    else if (!found) cnt = cnt + 6'd1;
                end
                y = {26'd0, cnt};
            end
            5'd20: begin  // CTZ: zeros below the lowest 1, 32 for 0
                for (int i = 0; i < 32; i++) begin
                    if (!found && a[i]) found = 1'b1;
                    else if (!found) cnt = cnt + 6'd1;
                end
                y = {26'd0, cnt};
            end
            5'd21: begin  // CPOP
                for (int i = 0; i < 32; i++) cnt = cnt + {5'd0, a[i]};
                y = {26'd0, cnt};
            end
            5'd22: y = {{24{a[7]}}, a[7:0]};                              // SEXT.B
            5'd23: y = {{16{a[15]}}, a[15:0]};                            // SEXT.H
            5'd24: y = {16'd0, a[15:0]};                                  // ZEXT.H
            5'd25: y = {a[7:0], a[15:8], a[23:16], a[31:24]};             // REV8
            5'd26: begin  // ORC.B
                for (int k = 0; k < 4; k++) y[8*k +: 8] = (a[8*k +: 8] != 8'd0) ? 8'hFF : 8'h00;
            end
            default: begin  // 27..31: illegal (SPEC 5)
                y = 32'd0;
                illegal = 1'b1;
            end
        endcase
        flags = {y[31], (y == 32'd0), c, v};
    end
endmodule
