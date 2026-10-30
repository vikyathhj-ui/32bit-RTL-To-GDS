// alu_top: RV32I + Zbb ALU (docs/SPEC.md).
//
// Pipeline (latency L = 2 for PIPE = 0, 3 for PIPE = 1; SPEC section 2, D-006):
//   S0   input registers: v0 (reset), op0/a0/b0 (load when in_valid)
//   S1   decode from the *registered* opcode; shared adder, shifter, counts,
//        logic and byte units -> three unit results + C/V + select
//   [P]  PIPE = 1 only: register after the adder/shifter stage (D-013)
//   S2   final mux, N/Z from that same y, illegal handling -> output registers
// Reset: rst_n is asynchronous assert; de-assertion must be synchronous to clk
// (the SoC's reset synchronizer provides it). Only valid bits are reset;
// data registers load only when their stage is valid and otherwise hold (D-010).
module alu_top #(
    parameter int ADDER = alu_pkg::ADDER_BEH,
    parameter int PIPE  = 0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        in_valid,
    input  logic [4:0]  op,
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic        out_valid,
    output logic [31:0] y,
    output logic [3:0]  flags,      // {N, Z, C, V}
    output logic        illegal_op
);
    import alu_pkg::*;

    // Unit select for the final mux.
    localparam logic [1:0] SEL_ADD   = 2'd0;  // adder group: ADD SUB SLT SLTU MIN MAX MINU MAXU
    localparam logic [1:0] SEL_SHIFT = 2'd1;  // SLL SRL SRA ROL ROR
    localparam logic [1:0] SEL_MISC  = 2'd2;  // logic, counts, byte/extend
    localparam logic [1:0] SEL_ZERO  = 2'd3;  // illegal opcode -> y = 0

    function automatic logic [31:0] rev32(input logic [31:0] x);
        for (int i = 0; i < 32; i++) rev32[i] = x[31-i];
    endfunction

    // ------------------------------------------------------------------ S0
    logic        v0;
    logic [4:0]  op0;
    logic [31:0] a0, b0;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) v0 <= 1'b0;
        else        v0 <= in_valid;
    end

    always_ff @(posedge clk) begin
        if (in_valid) begin
            op0 <= op;
            a0  <= a;
            b0  <= b;
        end
    end

    // ------------------------------------------------------------------ S1: decode
    logic use_sub;   // adder computes a0 - b0
    logic inv_b;     // b0 is inverted (subtract, or ANDN/ORN/XNOR)
    logic is_addsub; // C and V are architectural flags
    logic illegal;

    always_comb begin
        use_sub = 1'b0;
        case (op0)
            OP_SUB, OP_SLT, OP_SLTU, OP_MIN, OP_MAX, OP_MINU, OP_MAXU: use_sub = 1'b1;
            default:                                                   use_sub = 1'b0;
        endcase
    end
    assign inv_b     = use_sub | (op0 == OP_ANDN) | (op0 == OP_ORN) | (op0 == OP_XNOR);
    assign is_addsub = (op0 == OP_ADD) | (op0 == OP_SUB);
    assign illegal   = (op0 >= OP_ILLEGAL_MIN);

    // One inverter on b serves the subtractor and the negated logic ops
    // (the Zbb implementation hint, D-014).
    logic [31:0] bx;
    assign bx = inv_b ? ~b0 : b0;

    // ------------------------------------------------------------------ S1: shared adder
    logic [31:0] sum;
    logic        cout;
    logic        ovf, lt_s, lt_u;

    adder #(.ARCH(ADDER), .W(32)) u_adder (
        .a(a0), .b(bx), .cin(use_sub), .sum(sum), .cout(cout)
    );

    // Signed overflow of a0 + bx (+cin): operands agree in sign, result does not.
    assign ovf  = (a0[31] == bx[31]) && (sum[31] != a0[31]);
    // Comparison by subtraction: signed a < b <=> N xor V; unsigned a < b <=> borrow.
    assign lt_s = sum[31] ^ ovf;
    assign lt_u = ~cout;

    logic [31:0] r_add;
    always_comb begin
        case (op0)
            OP_SLT:  r_add = {31'd0, lt_s};
            OP_SLTU: r_add = {31'd0, lt_u};
            OP_MIN:  r_add = lt_s ? a0 : b0;
            OP_MAX:  r_add = lt_s ? b0 : a0;
            OP_MINU: r_add = lt_u ? a0 : b0;
            OP_MAXU: r_add = lt_u ? b0 : a0;
            default: r_add = sum;  // ADD, SUB
        endcase
    end

    // ------------------------------------------------------------------ S1: shifter
    logic [31:0] r_shift;

    shifter u_shifter (
        .a(a0), .s(b0[4:0]),
        .left((op0 == OP_SLL) | (op0 == OP_ROL)),
        .rotate((op0 == OP_ROL) | (op0 == OP_ROR)),
        .arith(op0 == OP_SRA),
        .y(r_shift)
    );

    // ------------------------------------------------------------------ S1: counts
    logic [5:0] n_lz, n_pop;

    // CTZ = CLZ of the bit-reversed operand: one tree for both (D-015).
    clz  #(.W(32)) u_clz  (.x((op0 == OP_CTZ) ? rev32(a0) : a0), .cnt(n_lz));
    cpop #(.W(32)) u_cpop (.x(a0), .cnt(n_pop));

    // ------------------------------------------------------------------ S1: logic + byte
    logic [31:0] r_misc;
    logic [31:0] orc;

    for (genvar k = 0; k < 4; k++) begin : g_orc
        assign orc[8*k +: 8] = {8{|a0[8*k +: 8]}};
    end

    always_comb begin
        case (op0)
            OP_AND, OP_ANDN: r_misc = a0 & bx;
            OP_OR,  OP_ORN:  r_misc = a0 | bx;
            OP_XOR, OP_XNOR: r_misc = a0 ^ bx;
            OP_CLZ, OP_CTZ:  r_misc = {26'd0, n_lz};
            OP_CPOP:         r_misc = {26'd0, n_pop};
            OP_SEXT_B:       r_misc = {{24{a0[7]}}, a0[7:0]};
            OP_SEXT_H:       r_misc = {{16{a0[15]}}, a0[15:0]};
            OP_ZEXT_H:       r_misc = {16'd0, a0[15:0]};
            OP_REV8:         r_misc = {a0[7:0], a0[15:8], a0[23:16], a0[31:24]};
            OP_ORC_B:        r_misc = orc;
            default:         r_misc = 32'd0;
        endcase
    end

    // ------------------------------------------------------------------ S1: result select, C/V
    logic [1:0] sel1;
    logic       c1, ovf1;

    always_comb begin
        if (illegal) begin
            sel1 = SEL_ZERO;
        end else begin
            case (op0)
                OP_ADD, OP_SUB, OP_SLT, OP_SLTU,
                OP_MIN, OP_MAX, OP_MINU, OP_MAXU:      sel1 = SEL_ADD;
                OP_SLL, OP_SRL, OP_SRA, OP_ROL, OP_ROR: sel1 = SEL_SHIFT;
                default:                                sel1 = SEL_MISC;
            endcase
        end
    end
    assign c1   = is_addsub & cout;
    assign ovf1 = is_addsub & ovf;

    // ------------------------------------------------------------------ optional PIPE register
    logic        v2;
    logic [31:0] r_add2, r_shift2, r_misc2;
    logic [1:0]  sel2;
    logic        c2, ovf2, illegal2;

    if (PIPE == 1) begin : g_pipe
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) v2 <= 1'b0;
            else        v2 <= v0;
        end
        always_ff @(posedge clk) begin
            if (v0) begin
                r_add2   <= r_add;
                r_shift2 <= r_shift;
                r_misc2  <= r_misc;
                sel2     <= sel1;
                c2       <= c1;
                ovf2     <= ovf1;
                illegal2 <= illegal;
            end
        end
    end else if (PIPE == 0) begin : g_nopipe
        assign v2       = v0;
        assign r_add2   = r_add;
        assign r_shift2 = r_shift;
        assign r_misc2  = r_misc;
        assign sel2     = sel1;
        assign c2       = c1;
        assign ovf2     = ovf1;
        assign illegal2 = illegal;
    end else begin : g_bad_pipe
        alu_top_PIPE_must_be_0_or_1 u_error ();
    end

    // ------------------------------------------------------------------ S2: final mux, flags, outputs
    logic [31:0] y_next;

    always_comb begin
        case (sel2)
            SEL_ADD:   y_next = r_add2;
            SEL_SHIFT: y_next = r_shift2;
            SEL_MISC:  y_next = r_misc2;
            default:   y_next = 32'd0;  // SEL_ZERO: illegal opcode
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) out_valid <= 1'b0;
        else        out_valid <= v2;
    end

    // Flags are computed from the same y_next that is registered into y,
    // so they can never be a cycle stale (legacy bug A3).
    always_ff @(posedge clk) begin
        if (v2) begin
            y          <= y_next;
            flags      <= {y_next[31], (y_next == 32'd0), c2, ovf2};
            illegal_op <= illegal2;
        end
    end
endmodule
