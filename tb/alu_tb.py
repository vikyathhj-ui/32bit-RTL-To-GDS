"""cocotb testbench for alu_top (BRIEF A3, docs/SPEC.md).

Self-checking against the golden model model/alu_ref.py. One operation can be
issued per cycle. Inputs are driven, and outputs sampled, on the falling clock
edge, so every value seen is the settled result of the previous rising edge.

Timing check: an operation driven at falling edge k is sampled by rising edge
k+1; its result must be visible at falling edge k+L (L = 2 for PIPE = 0, 3 for
PIPE = 1; SPEC section 2). The scoreboard checks the cycle, not just the order.

Environment (set by scripts/run_sim.py):
  ALU_PIPE      0 or 1 (must match the PIPE parameter the design was built with)
  ALU_VECTORS   random vectors for test_random (default 1_000_000)
  ALU_SEED      seed for test_random's stimulus generator (default 1)
  ALU_CLK_NS    clock period in ns (default 10; the gate-level power runs use the
                architecture's own closing period)
  ALU_COV_OUT   path for the coverage JSON (default: none written)
"""

from __future__ import annotations

import collections
import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "model"))
sys.path.insert(0, str(REPO / "tb"))

import alu_coverage as coverage  # noqa: E402
from alu_ref import ILLEGAL_OPCODES, MASK, NAMES, OPCODES, alu  # noqa: E402

PIPE = int(os.environ.get("ALU_PIPE", "0"))
LATENCY = 2 + PIPE
INT_MIN, INT_MAX = 0x80000000, 0x7FFFFFFF
CORNERS = [0, 1, MASK, INT_MIN, INT_MAX, 0xAAAAAAAA, 0x55555555, 0x80000001, 0x7FFFFFFE]
SHIFT_OPS = {OPCODES[n] for n in ("SLL", "SRL", "SRA", "ROL", "ROR")}
LEGAL = sorted(NAMES)


class Mismatch(Exception):
    pass


class Bench:
    """Driver + scoreboard + monitor, stepped once per clock cycle."""

    def __init__(self, dut):
        self.dut = dut
        self.cycle = 0
        self.expect = collections.deque()  # (issue_cycle, op, a, b, AluResult)
        self.checked = 0
        self.errors = 0
        self.max_report = 20

    async def start(self):
        # Period in ps so fractional ns periods (e.g. 20.25) are exact; default 10 ns.
        period_ps = round(float(os.environ.get("ALU_CLK_NS", "10")) * 1000)
        cocotb.start_soon(Clock(self.dut.clk, period_ps, unit="ps").start())
        self.dut.in_valid.value = 0
        self.dut.op.value = 0
        self.dut.a.value = 0
        self.dut.b.value = 0
        await self.reset(3)

    async def reset(self, cycles: int = 2):
        """Assert rst_n for `cycles` cycles. In-flight operations are discarded."""
        self.dut.rst_n.value = 0
        self.dut.in_valid.value = 0
        self.expect.clear()
        for _ in range(cycles):
            await FallingEdge(self.dut.clk)
            self.cycle += 1
            if int(self.dut.out_valid.value) != 0:
                self._fail("out_valid=1 during reset")
        self.dut.rst_n.value = 1

    def _fail(self, msg: str):
        self.errors += 1
        if self.errors <= self.max_report:
            self.dut._log.error("FAIL cycle %d: %s", self.cycle, msg)

    def _monitor(self):
        """Check the outputs that are visible at this falling edge."""
        if int(self.dut.out_valid.value):
            if not self.expect:
                self._fail("out_valid=1 with no operation in flight")
                return
            issue, op, a, b, exp = self.expect.popleft()
            if self.cycle != issue + LATENCY:
                self._fail(f"latency: issued at {issue}, result at {self.cycle}, expected L={LATENCY}")
            y = int(self.dut.y.value)
            flags = int(self.dut.flags.value)
            ill = int(self.dut.illegal_op.value)
            exp_flags = (exp.n << 3) | (exp.z << 2) | (exp.c << 1) | exp.v
            if y != exp.y or flags != exp_flags or ill != exp.illegal:
                name = NAMES.get(op, f"ILLEGAL({op})")
                self._fail(f"{name} a=0x{a:08x} b=0x{b:08x}: got y=0x{y:08x} NZCV={flags:04b} "
                           f"illegal={ill}; expected y=0x{exp.y:08x} NZCV={exp_flags:04b} "
                           f"illegal={exp.illegal}")
            coverage.sample(op, a, b, exp)
            self.checked += 1
        elif self.expect and self.expect[0][0] + LATENCY == self.cycle:
            self._fail(f"missing result for operation issued at cycle {self.expect[0][0]}")
            self.expect.popleft()

    async def step(self, op: int | None = None, a: int = 0, b: int = 0):
        """Advance one cycle: check outputs, then drive the next input (None = bubble)."""
        await FallingEdge(self.dut.clk)
        self.cycle += 1
        self._monitor()
        if op is None:
            self.dut.in_valid.value = 0
        else:
            self.dut.in_valid.value = 1
            self.dut.op.value = op
            self.dut.a.value = a
            self.dut.b.value = b
            # Sampled by the next rising edge; result due at falling edge cycle + L.
            self.expect.append((self.cycle, op, a, b, alu(op, a, b)))

    async def drain(self):
        for _ in range(LATENCY + 2):
            await self.step(None)
        if self.expect:
            self._fail(f"{len(self.expect)} operations never produced a result")

    def finish(self, test: str, extra: str = ""):
        status = "PASS" if self.errors == 0 else "FAIL"
        self.dut._log.info("%s %s: %d results checked, %d errors%s", status, test, self.checked,
                           self.errors, extra)
        cov_out = os.environ.get("ALU_COV_OUT")
        if cov_out:
            s = coverage.report(Path(cov_out))
            self.dut._log.info("coverage so far: %.2f%% (%d/%d bins)", s["percent"], s["covered"], s["bins"])
        assert self.errors == 0, f"{test}: {self.errors} errors (first {self.max_report} logged above)"


# ---------------------------------------------------------------- stimulus helpers

def directed_vectors():
    """Deterministic corner stimulus (BRIEF A3 'Directed corners')."""
    vecs = []
    single_bits = [1 << i for i in range(32)]
    for op in LEGAL:
        for a in CORNERS:
            for b in CORNERS:
                vecs.append((op, a, b))
    for op in SHIFT_OPS:                                    # shift amounts 0/1/31 and b[4:0] only
        for a in CORNERS:
            for s in (0, 1, 2, 15, 16, 30, 31, 32, 33, 63, 0xFFFFFFE0, 0xFFFFFFFF):
                vecs.append((op, a, s))
    for x in single_bits + [(1 << i) - 1 for i in range(33)] + [MASK << i & MASK for i in range(33)]:
        vecs.append((OPCODES["CLZ"], x, 0))                 # every CLZ/CTZ result 0..32
        vecs.append((OPCODES["CTZ"], x, 0))
        vecs.append((OPCODES["CPOP"], x, 0))
    add, sub = OPCODES["ADD"], OPCODES["SUB"]
    vecs += [(add, MASK, 1), (add, INT_MAX, 1), (add, INT_MIN, INT_MIN), (add, 0, 0),
             (sub, 5, 5), (sub, 3, 5), (sub, INT_MIN, 1), (sub, INT_MAX, MASK), (sub, 0, INT_MIN)]
    for op in ILLEGAL_OPCODES:
        for a, b in ((0, 0), (MASK, MASK), (0x12345678, 0x9ABCDEF0)):
            vecs.append((op, a, b))
    vecs += [(OPCODES["ORN"], 0, MASK), (OPCODES["ORC.B"], 0x00FF0000, 0), (OPCODES["REV8"], 0x80, 0)]
    return vecs


def rand_operand(rng: random.Random) -> int:
    """Constrained-random operand: corner-heavy mix (DECISIONS D-019)."""
    r = rng.random()
    if r < 0.05:
        return 0
    if r < 0.15:
        return rng.randint(1, 255)
    if r < 0.25:
        return (-rng.randint(1, 256)) & MASK
    if r < 0.29:
        return INT_MAX
    if r < 0.33:
        return INT_MIN
    if r < 0.39:
        return rng.choice((INT_MAX - rng.randint(0, 255), INT_MIN + rng.randint(0, 255)))
    if r < 0.47:
        return 1 << rng.randrange(32)
    if r < 0.52:
        return rng.choice((0xAAAAAAAA, 0x55555555, MASK, 0xFFFF0000, 0x0000FFFF, 0xFF00FF00))
    if r < 0.60:                                            # long runs of zeros at either end
        x = rng.getrandbits(32) | 1
        return (x >> rng.randrange(33)) if rng.random() < 0.5 else (x << rng.randrange(33)) & MASK
    return rng.getrandbits(32)


def rand_op(rng: random.Random) -> int:
    return rng.choice(ILLEGAL_OPCODES) if rng.random() < 0.03 else rng.choice(LEGAL)


def rand_b(rng: random.Random, op: int) -> int:
    if op in SHIFT_OPS and rng.random() < 0.4:
        s = rng.choice((0, 1, 31))
        return (rng.getrandbits(27) << 5) | s                # upper bits must be ignored
    return rand_operand(rng)


# ---------------------------------------------------------------- tests

@cocotb.test()
async def test_directed(dut):
    """Directed corners, back-to-back op changes, bubbles and a mid-stream reset."""
    tb = Bench(dut)
    await tb.start()
    vecs = directed_vectors()
    for op, a, b in vecs:                                   # back-to-back: op changes every cycle
        await tb.step(op, a, b)
    await tb.drain()
    rng = random.Random(1)
    for op, a, b in vecs[:500]:                             # same stimulus with bubbles
        if rng.random() < 0.3:
            await tb.step(None)
        await tb.step(op, a, b)
    await tb.reset(2)                                       # in-flight results must vanish
    for op, a, b in vecs[500:600]:
        await tb.step(op, a, b)
    await tb.drain()
    tb.finish("test_directed", f" ({len(vecs)} directed vectors, L={LATENCY})")


@cocotb.test()
async def test_random(dut):
    """Constrained-random stream with bubbles and occasional resets.

    Runs until exactly ALU_VECTORS results have been *checked*: operations
    flushed by a mid-stream reset are not counted and are replaced.
    """
    n = int(os.environ.get("ALU_VECTORS", "1000000"))
    seed = int(os.environ.get("ALU_SEED", "1"))
    rng = random.Random(seed)
    tb = Bench(dut)
    await tb.start()
    issued = 0
    while tb.checked + len(tb.expect) < n:                  # checked + in flight
        if rng.random() < 0.10:
            await tb.step(None)                             # bubble
            continue
        if issued and issued % 250_000 == 0 and rng.random() < 0.5:
            await tb.reset(2)                               # flushes in-flight ops
        op = rand_op(rng)
        await tb.step(op, rand_operand(rng), rand_b(rng, op))
        issued += 1
    await tb.drain()
    if tb.checked != n:
        tb._fail(f"checked {tb.checked} results, expected exactly {n}")
    tb.finish("test_random", f" ({n} random results checked, {issued} issued, "
                             f"{issued - tb.checked} flushed by reset, seed={seed}, L={LATENCY})")
