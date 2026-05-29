module alu32 (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] A,
    input  wire [31:0] B,
    input  wire [4:0]  opcode,
    input  wire        valid_in,
    output reg  [31:0] result,
    output reg         zero,
    output reg         carry,
    output reg         overflow,
    output reg         negative,
    output reg         valid_out
);

localparam ADD=0,SUB=1,AND=2,OR=3,XOR=4,NOR=5,NAND=6,NOT=7;
localparam SLL=8,SRL=9,SRA=10,ROL=11,ROR=12;
localparam SLT=13,SLTU=14,SEQ=15,SNE=16,SGE=17;
localparam ADDC=18,SUBB=19,ABS=20,MAX=21,MIN=22;
localparam PASS_A=23,PASS_B=24;

wire [32:0] add_result = {1'b0,A} + {1'b0,B};
wire [32:0] sub_result = {1'b0,A} - {1'b0,B};
wire [4:0]  shamt = B[4:0];
wire signed_lt = ($signed(A) < $signed(B));
wire [31:0] rol_result = (A << shamt) | (A >> (32-shamt));
wire [31:0] ror_result = (A >> shamt) | (A << (32-shamt));
wire [31:0] abs_result = A[31] ? (~A + 1) : A;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        result <= 0; zero <= 0; carry <= 0;
        overflow <= 0; negative <= 0; valid_out <= 0;
    end else begin
        valid_out <= valid_in;
        carry    <= 0;
        overflow <= 0;
        case (opcode)
            ADD:  begin result<=add_result[31:0]; carry<=add_result[32];
                  overflow<=(~A[31]&~B[31]&add_result[31])|(A[31]&B[31]&~add_result[31]); end
            SUB:  begin result<=sub_result[31:0]; carry<=sub_result[32];
                  overflow<=(~A[31]&B[31]&sub_result[31])|(A[31]&~B[31]&~sub_result[31]); end
            AND:  result <= A & B;
            OR:   result <= A | B;
            XOR:  result <= A ^ B;
            NOR:  result <= ~(A | B);
            NAND: result <= ~(A & B);
            NOT:  result <= ~A;
            SLL:  result <= A << shamt;
            SRL:  result <= A >> shamt;
            SRA:  result <= $signed(A) >>> shamt;
            ROL:  result <= rol_result;
            ROR:  result <= ror_result;
            SLT:  result <= {31'd0, signed_lt};
            SLTU: result <= {31'd0, (A < B)};
            SEQ:  result <= {31'd0, (A == B)};
            SNE:  result <= {31'd0, (A != B)};
            SGE:  result <= {31'd0, ($signed(A) >= $signed(B))};
            ADDC: begin result<=add_result[31:0]; carry<=add_result[32]; end
            SUBB: begin result<=sub_result[31:0]; carry<=sub_result[32]; end
            ABS:  result <= abs_result;
            MAX:  result <= signed_lt ? B : A;
            MIN:  result <= signed_lt ? A : B;
            PASS_A: result <= A;
            PASS_B: result <= B;
            default: result <= 32'd0;
        endcase
        zero     <= (result == 32'd0);
        negative <= result[31];
    end
end
endmodule
