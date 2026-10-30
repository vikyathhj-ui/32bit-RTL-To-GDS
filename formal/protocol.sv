// protocol: latency proof (BRIEF A3 formal 3).
// out_valid at cycle t + L must equal in_valid at cycle t, where L = 2 for
// PIPE = 0 and 3 for PIPE = 1 (SPEC section 2), with any reset in between
// clearing the operations in flight. The shadow is a plain L-deep shift
// register of in_valid with the same reset; the datapath is irrelevant here.
module protocol #(
    parameter int PIPE = 0
) (
    input logic        clk,
    input logic        rst_n,
    input logic        in_valid,
    input logic [4:0]  op,
    input logic [31:0] a,
    input logic [31:0] b
);
    localparam int L = 2 + PIPE;

    logic        out_valid, illegal_op;
    logic [31:0] y;
    logic [3:0]  flags;

    alu_top #(.ADDER(7), .PIPE(PIPE)) dut (
        .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .op(op), .a(a), .b(b),
        .out_valid(out_valid), .y(y), .flags(flags), .illegal_op(illegal_op)
    );

    logic [L-1:0] sh;  // sh[k] = in_valid delayed by k+1 cycles
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) sh <= '0;
        else        sh <= {sh[L-2:0], in_valid};
    end

    logic init = 1'b1;
    logic [L-1:0] since_reset;  // shifts in 1s after reset; all 1s = L cycles out of reset
    always_ff @(posedge clk) init <= 1'b0;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) since_reset <= '0;
        else        since_reset <= {since_reset[L-2:0], 1'b1};
    end

    always_comb begin
        if (init) assume (!rst_n);
        if (!init) begin
            assert (out_valid == sh[L-1]);                 // exact latency L
            if (!since_reset[L-1]) assert (!out_valid);    // nothing valid in the first L cycles
        end
    end
endmodule
