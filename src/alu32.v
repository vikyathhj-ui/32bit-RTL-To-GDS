module alu32 (
    input  [31:0] A,
    input  [31:0] B,
    input  [3:0]  opcode,
    output reg [31:0] result,
    output reg        zero,
    output reg        carry,
    output reg        overflow
);

always @(*) begin
    carry    = 0;
    overflow = 0;
    case (opcode)
        4'b0000: {carry, result} = A + B;
        4'b0001: {carry, result} = A - B;
        4'b0010: result = A & B;
        4'b0011: result = A | B;
        4'b0100: result = A ^ B;
        4'b0101: result = ~A;
        4'b0110: result = A << B[4:0];
        4'b0111: result = A >> B[4:0];
        4'b1000: result = $signed(A) >>> B[4:0];
        4'b1001: result = (A < B) ? 32'd1 : 32'd0;
        4'b1010: result = A * B;
        4'b1011: result = (A == B) ? 32'd1 : 32'd0;
        default: result = 32'd0;
    endcase
    zero = (result == 32'd0);
    if (opcode == 4'b0000)
        overflow = (~A[31] & ~B[31] & result[31]) |
                   (A[31] & B[31] & ~result[31]);
    if (opcode == 4'b0001)
        overflow = (~A[31] & B[31] & result[31]) |
                   (A[31] & ~B[31] & ~result[31]);
end

endmodule
