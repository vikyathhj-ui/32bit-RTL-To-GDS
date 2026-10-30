// adder_miter: proves one adder architecture equals a + b + cin for ALL inputs
// (BRIEF A3 formal item 1). The design and the reference (`+`) share inputs; the
// assertion says their outputs can never differ. There is no state, so the
// solver checks all 2^65 input combinations symbolically in one step.
module adder_miter #(
    parameter int ARCH = 7  // alu_pkg::ADDER_* code
) (
    input logic [31:0] a,
    input logic [31:0] b,
    input logic        cin
);
    logic [31:0] sum;
    logic        cout;

    adder #(.ARCH(ARCH), .W(32)) dut (.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));

    always_comb begin
        assert ({cout, sum} == ({1'b0, a} + {1'b0, b} + {32'd0, cin}));
    end
endmodule
