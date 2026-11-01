// adder_wrap: register-to-register harness around one adder architecture, used
// only by the ABC structure experiment (scripts/abc_exp.py, DECISIONS D-026).
// Isolating the adder means the measured critical path is the adder's own,
// not the ALU's shifter or CPOP.
module adder_wrap #(
    parameter int ARCH = alu_pkg::ADDER_BEH
) (
    input  logic        clk,
    input  logic [31:0] a,
    input  logic [31:0] b,
    input  logic        cin,
    output logic [31:0] sum,
    output logic        cout
);
    logic [31:0] a_q, b_q, s;
    logic        c_q, co;

    always_ff @(posedge clk) begin
        a_q  <= a;
        b_q  <= b;
        c_q  <= cin;
        sum  <= s;
        cout <= co;
    end

    adder #(.ARCH(ARCH), .W(32)) u_add (.a(a_q), .b(b_q), .cin(c_q), .sum(s), .cout(co));
endmodule
