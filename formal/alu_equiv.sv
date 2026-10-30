// alu_equiv: full-ALU equivalence proof harness (BRIEF A3 formal 2).
//
// alu_top (any ADDER, PIPE) runs next to a shadow pipeline that carries the
// same (op, a, b) with the timing from SPEC section 2. At the end of the
// shadow pipeline, the behavioural reference (alu_ref_beh) computes the
// expected result, which is registered like the DUT's outputs. Whenever
// out_valid = 1, y, flags and illegal_op must equal the reference; and
// out_valid itself must equal the shadow valid bit. Inputs are unconstrained
// except that reset is asserted in the first cycle (reset may also be applied
// again at any later time).
module alu_equiv #(
    parameter int ADDER = 7,
    parameter int PIPE  = 0
) (
    input logic        clk,
    input logic        rst_n,
    input logic        in_valid,
    input logic [4:0]  op,
    input logic [31:0] a,
    input logic [31:0] b
);
    logic        out_valid, illegal_op;
    logic [31:0] y;
    logic [3:0]  flags;

    alu_top #(.ADDER(ADDER), .PIPE(PIPE)) dut (
        .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .op(op), .a(a), .b(b),
        .out_valid(out_valid), .y(y), .flags(flags), .illegal_op(illegal_op)
    );

    // ---- shadow pipeline: stage 0 (input registers)
    logic        s_v0;
    logic [4:0]  s_op0;
    logic [31:0] s_a0, s_b0;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) s_v0 <= 1'b0;
        else        s_v0 <= in_valid;
    end
    always_ff @(posedge clk) begin
        if (in_valid) begin
            s_op0 <= op;
            s_a0  <= a;
            s_b0  <= b;
        end
    end

    // ---- optional extra stage when PIPE = 1
    logic        s_vl;
    logic [4:0]  s_opl;
    logic [31:0] s_al, s_bl;
    if (PIPE == 1) begin : g_pipe
        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) s_vl <= 1'b0;
            else        s_vl <= s_v0;
        end
        always_ff @(posedge clk) begin
            if (s_v0) begin
                s_opl <= s_op0;
                s_al  <= s_a0;
                s_bl  <= s_b0;
            end
        end
    end else begin : g_nopipe
        assign s_vl  = s_v0;
        assign s_opl = s_op0;
        assign s_al  = s_a0;
        assign s_bl  = s_b0;
    end

    // ---- reference result, registered like the DUT outputs
    logic [31:0] r_y;
    logic [3:0]  r_flags;
    logic        r_ill;
    alu_ref_beh u_ref (.op(s_opl), .a(s_al), .b(s_bl), .y(r_y), .flags(r_flags), .illegal(r_ill));

    logic        e_valid;
    logic [31:0] e_y;
    logic [3:0]  e_flags;
    logic        e_ill;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) e_valid <= 1'b0;
        else        e_valid <= s_vl;
    end
    always_ff @(posedge clk) begin
        if (s_vl) begin
            e_y     <= r_y;
            e_flags <= r_flags;
            e_ill   <= r_ill;
        end
    end

    // ---- properties
    logic init = 1'b1;
    always_ff @(posedge clk) init <= 1'b0;

    always_comb begin
        if (init) assume (!rst_n);
        if (!init) begin
            assert (out_valid == e_valid);
            if (out_valid) begin
                assert (y == e_y);
                assert (flags == e_flags);
                assert (illegal_op == e_ill);
            end
        end
    end
endmodule
