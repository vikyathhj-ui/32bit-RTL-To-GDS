// Audit probe for legacy/alu32_final.v (Phase 0). Not part of the new design.
// Run: docker exec -w /foss/projects/32bit-RTL-To-GDS iic-osic bash -lc 'scripts/legacy_probe.sh'
`timescale 1ns/1ps
module tb;
  reg clk=0, rst=1, vin=0; reg [31:0] A=0,B=0; reg [4:0] op=0;
  wire [31:0] y; wire z,n,c,v,vout;
  alu32_final dut(.clk(clk),.rst(rst),.A(A),.B(B),.opcode(op),.valid_in(vin),
    .result(y),.zero(z),.negative(n),.carry(c),.overflow(v),.valid_out(vout));
  always #5 clk=~clk;
  // hold op stable for 3 cycles then sample (best case for the legacy design)
  task hold(input [4:0] o, input [31:0] a, input [31:0] b, input [31:0] exp, input [8*8-1:0] nm);
    begin op=o; A=a; B=b; vin=1; repeat(3) @(posedge clk); #1;
      $display("%-6s op=%2d A=%h B=%h -> y=%h exp=%h %s z=%b", nm, o, a, b, y, exp, (y===exp)?"OK  ":"FAIL", z); end
  endtask
  initial begin
    repeat(2) @(posedge clk); rst=0;
    hold(0, 32'd5, 32'd7, 32'd12, "ADD");
    hold(8, 32'hF0F0F0F0, 32'hFF00FF00, 32'hF00FF00F, "XNOR");
    hold(12, 32'h80000001, 32'd0, 32'h80000001, "ROL0");
    hold(12, 32'h80000001, 32'd1, 32'h00000003, "ROL1");
    hold(13, 32'h00000003, 32'd1, 32'h80000001, "ROR1");
    hold(20, 32'hFFFFFFFB, 32'd0, 32'd5, "ABS");
    hold(23, 32'h00010000, 32'd0, 32'd15, "CLZ");
    hold(24, 32'hF000000F, 32'd0, 32'd8, "POP");
    // back-to-back: ADD then AND in consecutive cycles (normal pipelined use)
    op=0; A=10; B=20; @(posedge clk); #1; op=2; A=32'hFF; B=32'h0F; @(posedge clk); #1;
    $display("b2b: after ADD(10,20) issued, cycle+1 y=%h (exp 0000001e)", y); @(posedge clk); #1;
    $display("b2b: after AND(ff,0f) issued, cycle+1 y=%h (exp 0000000f)", y);
    // zero flag staleness: ADD giving 0, single cycle
    op=0; A=0; B=0; repeat(3) @(posedge clk); #1; $display("zero after y=0 stable: z=%b", z);
    op=0; A=1; B=0; @(posedge clk); @(posedge clk); #1; $display("y=%h z=%b (z should be 0 when y!=0)", y, z);
    // valid_out stickiness
    vin=0; repeat(4) @(posedge clk); #1; $display("valid_in=0 for 4 cycles -> valid_out=%b (exp 0)", vout);
    $finish;
  end
endmodule
