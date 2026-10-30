module alu32_final (
    input         clk,
    input         rst,
    input  [31:0] A,
    input  [31:0] B,
    input  [4:0]  opcode,
    input         valid_in,
    output reg [31:0] result,
    output reg        zero,
    output reg        negative,
    output reg        carry,
    output reg        overflow,
    output reg        valid_out
);

// ============================================
// CARRY LOOKAHEAD ADDER
// ============================================
function [32:0] cla_add;
    input [31:0] X, Y;
    input        cin;
    reg [31:0] G, P, C;
    integer i;
    begin
        G = X & Y;
        P = X | Y;
        C[0] = cin;
        for (i = 1; i < 32; i = i + 1)
            C[i] = G[i-1] | (P[i-1] & C[i-1]);
        cla_add[31:0] = X ^ Y ^ C[31:0];
        cla_add[32]   = G[31] | (P[31] & C[31]);
    end
endfunction

// ============================================
// COUNT LEADING ZEROS (CLZ)
// ============================================
function [4:0] clz32;
    input [31:0] X;
    reg [4:0] count;
    integer i;
    begin
        count = 0;
        for (i = 31; i >= 0; i = i - 1)
            if (X[i] == 0 && count == (31-i)) count = count + 1;
        clz32 = count;
    end
endfunction

// ============================================
// POPULATION COUNT (POPCOUNT)
// ============================================
function [5:0] popcount32;
    input [31:0] X;
    reg [5:0] count;
    integer i;
    begin
        count = 0;
        for (i = 0; i < 32; i = i + 1)
            count = count + X[i];
        popcount32 = count;
    end
endfunction

// ============================================
// BIT REVERSAL
// ============================================
function [31:0] bitrev32;
    input [31:0] X;
    integer i;
    begin
        for (i = 0; i < 32; i = i + 1)
            bitrev32[i] = X[31-i];
    end
endfunction

// ============================================
// CLOCK GATING
// ============================================
wire en_arith   = valid_in && (opcode <= 5'b00001);
wire en_logic   = valid_in && (opcode >= 5'b00010 && opcode <= 5'b00111);
wire en_shift   = valid_in && (opcode >= 5'b01000 && opcode <= 5'b01100);
wire en_compare = valid_in && (opcode >= 5'b01101 && opcode <= 5'b10011);
wire en_special = valid_in && (opcode >= 5'b10000);

reg cg_arith, cg_logic, cg_shift, cg_compare, cg_special;
always @(clk or en_arith)   if (!clk) cg_arith   <= en_arith;
always @(clk or en_logic)   if (!clk) cg_logic   <= en_logic;
always @(clk or en_shift)   if (!clk) cg_shift   <= en_shift;
always @(clk or en_compare) if (!clk) cg_compare <= en_compare;
always @(clk or en_special) if (!clk) cg_special <= en_special;

wire clk_arith   = clk & cg_arith;
wire clk_logic   = clk & cg_logic;
wire clk_shift   = clk & cg_shift;
wire clk_compare = clk & cg_compare;
wire clk_special = clk & cg_special;

// ============================================
// STAGE 1A — ARITHMETIC (CLA)
// opcodes: 00000=ADD 00001=SUB
// ============================================
reg [31:0] s_add, s_sub;
reg        s_carry_add, s_carry_sub;
reg [31:0] s_A, s_B;
reg [4:0]  s_opcode;
reg        s_valid;

always @(posedge clk_arith or posedge rst) begin
    if (rst) s_valid <= 0;
    else begin
        s_A     <= A; s_B <= B;
        s_opcode<= opcode; s_valid <= valid_in;
        {s_carry_add, s_add} <= cla_add(A, B, 0);
        {s_carry_sub, s_sub} <= cla_add(A, ~B, 1);
    end
end

// ============================================
// STAGE 1B — LOGIC
// 00010=AND 00011=OR 00100=XOR 00101=NOT
// 00110=NAND 00111=NOR
// ============================================
reg [31:0] l_and, l_or, l_xor, l_not, l_nand, l_nor, l_xnor;
reg [4:0]  l_opcode;
reg        l_valid;

always @(posedge clk_logic or posedge rst) begin
    if (rst) l_valid <= 0;
    else begin
        l_opcode <= opcode; l_valid <= valid_in;
        l_and  <= A & B;
        l_or   <= A | B;
        l_xor  <= A ^ B;
        l_not  <= ~A;
        l_nand <= ~(A & B);
        l_nor  <= ~(A | B);
        l_xnor <= ~(A ^ B);
    end
end

// ============================================
// STAGE 1C — SHIFT/ROTATE
// 01000=SHL 01001=SHR 01010=ASR
// 01011=ROL 01100=ROR
// ============================================
reg [31:0] sh_shl, sh_shr, sh_asr, sh_rol, sh_ror;
reg [4:0]  sh_opcode;
reg        sh_valid;

always @(posedge clk_shift or posedge rst) begin
    if (rst) sh_valid <= 0;
    else begin
        sh_opcode <= opcode; sh_valid <= valid_in;
        sh_shl <= A << B[4:0];
        sh_shr <= A >> B[4:0];
        sh_asr <= $signed(A) >>> B[4:0];
        sh_rol <= (A << B[4:0]) | (A >> (32-B[4:0]));
        sh_ror <= (A >> B[4:0]) | (A << (32-B[4:0]));
    end
end

// ============================================
// STAGE 1D — COMPARE
// 01101=SLT 01110=SGT 01111=EQ
// ============================================
reg [31:0] c_slt, c_sgt, c_eq, c_sltu, c_sgtu, c_neq;
reg [4:0]  c_opcode;
reg        c_valid;

always @(posedge clk_compare or posedge rst) begin
    if (rst) c_valid <= 0;
    else begin
        c_opcode <= opcode; c_valid <= valid_in;
        c_slt  <= ($signed(A)   <  $signed(B))   ? 32'd1 : 32'd0;
        c_sgt  <= ($signed(A)   >  $signed(B))   ? 32'd1 : 32'd0;
        c_eq   <= (A == B)                        ? 32'd1 : 32'd0;
        c_sltu <= ($unsigned(A) <  $unsigned(B))  ? 32'd1 : 32'd0;
        c_sgtu <= ($unsigned(A) >  $unsigned(B))  ? 32'd1 : 32'd0;
        c_neq  <= (A != B)                        ? 32'd1 : 32'd0;
    end
end

// ============================================
// STAGE 1E — SPECIAL OPS
// 10000=ABS 10001=MAX 10010=MIN 10011=CLZ
// 10100=POPCOUNT 10101=BREV 10110=SWAP
// 10111=PASS_A 11000=PASS_B
// ============================================
reg [31:0] sp_abs, sp_max, sp_min;
reg [31:0] sp_clz, sp_pop, sp_brev, sp_swap;
reg [31:0] sp_passA, sp_passB;
reg [4:0]  sp_opcode;
reg        sp_valid;

always @(posedge clk_special or posedge rst) begin
    if (rst) sp_valid <= 0;
    else begin
        sp_opcode <= opcode; sp_valid <= valid_in;
        sp_abs   <= ($signed(A) < 0) ? (~A+1) : A;
        sp_max   <= ($signed(A) > $signed(B)) ? A : B;
        sp_min   <= ($signed(A) < $signed(B)) ? A : B;
        sp_clz   <= {27'd0, clz32(A)};
        sp_pop   <= {26'd0, popcount32(A)};
        sp_brev  <= bitrev32(A);
        sp_swap  <= {A[15:0], A[31:16]};
        sp_passA <= A;
        sp_passB <= B;
    end
end

// ============================================
// STAGE 2 — RESULT SELECT + FLAGS
// ============================================
always @(posedge clk or posedge rst) begin
    if (rst) begin
        valid_out <= 0; result <= 0;
        carry <= 0; overflow <= 0;
    end else begin
        valid_out <= s_valid|l_valid|sh_valid|c_valid|sp_valid;
        carry <= 0; overflow <= 0;

        case (opcode)
            // Arithmetic
            5'b00000: begin result<=s_add; carry<=s_carry_add;
                overflow<=(~s_A[31]&~s_B[31]&s_add[31])|(s_A[31]&s_B[31]&~s_add[31]); end
            5'b00001: begin result<=s_sub; carry<=s_carry_sub;
                overflow<=(~s_A[31]&s_B[31]&s_sub[31])|(s_A[31]&~s_B[31]&~s_sub[31]); end
            // Logic
            5'b00010: result <= l_and;
            5'b00011: result <= l_or;
            5'b00100: result <= l_xor;
            5'b00101: result <= l_not;
            5'b00110: result <= l_nand;
            5'b00111: result <= l_nor;
            5'b01000: result <= l_xnor;  // XNOR added
            // Shift/Rotate
            5'b01001: result <= sh_shl;
            5'b01010: result <= sh_shr;
            5'b01011: result <= sh_asr;
            5'b01100: result <= sh_rol;
            5'b01101: result <= sh_ror;  // was compare before
            // Compare
            5'b01110: result <= c_slt;
            5'b01111: result <= c_sgt;
            5'b10000: result <= c_eq;
            5'b10001: result <= c_sltu;  // unsigned SLT
            5'b10010: result <= c_sgtu;  // unsigned SGT
            5'b10011: result <= c_neq;   // not equal
            // Special
            5'b10100: result <= sp_abs;
            5'b10101: result <= sp_max;
            5'b10110: result <= sp_min;
            5'b10111: result <= sp_clz;
            5'b11000: result <= sp_pop;
            5'b11001: result <= sp_brev;
            5'b11010: result <= sp_swap;
            5'b11011: result <= sp_passA;
            5'b11100: result <= sp_passB;
            default:  result <= 32'd0;
        endcase

        zero     <= (result == 32'd0);
        negative <= result[31];
    end
end

endmodule
