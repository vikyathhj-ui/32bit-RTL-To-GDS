"""Gate-level power workload for alu_top (BRIEF A4 power, DECISIONS D-025).

Drives the post-route netlist (scripts/gls_power.py builds it with the PDK's
functional cell models) with the brief's operation mix, back-to-back (one op
per cycle), and checks every result against model/alu_ref.py with the same
scoreboard as tb/alu_tb.py, so the netlist is functionally verified too. A VCD
of the whole netlist is dumped by tb/gls_dump.v for OpenSTA read_vcd.

Mix (BRIEF A4): 50% add/sub, 20% logic, 20% shift, 10% Zbb.
  add/sub = ADD, SUB          logic = AND, OR, XOR       shift = SLL, SRL, SRA
  Zbb     = all 17 Zbb ops, uniformly
Operands are uniform 32-bit random (data-dependent activity, no corner bias).

Environment: ALU_OPS (default 10000), ALU_SEED, ALU_CLK_NS, ALU_PIPE.
"""

import os
import random
import sys
from pathlib import Path

import cocotb

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "model"))
sys.path.insert(0, str(REPO / "tb"))

from alu_ref import OPCODES  # noqa: E402
from alu_tb import Bench  # noqa: E402

GROUPS = [
    (0.50, ["ADD", "SUB"]),
    (0.20, ["AND", "OR", "XOR"]),
    (0.20, ["SLL", "SRL", "SRA"]),
    (0.10, ["MIN", "MAX", "MINU", "MAXU", "ANDN", "ORN", "XNOR", "ROL", "ROR",
            "CLZ", "CTZ", "CPOP", "SEXT.B", "SEXT.H", "ZEXT.H", "REV8", "ORC.B"]),
]


def pick_op(rng: random.Random) -> int:
    r = rng.random()
    acc = 0.0
    for weight, names in GROUPS:
        acc += weight
        if r < acc:
            return OPCODES[rng.choice(names)]
    return OPCODES[rng.choice(GROUPS[-1][1])]


@cocotb.test()
async def test_workload(dut):
    """Back-to-back workload mix, every result checked against the golden model."""
    n = int(os.environ.get("ALU_OPS", "10000"))
    rng = random.Random(int(os.environ.get("ALU_SEED", "1")))
    tb = Bench(dut)
    await tb.start()
    counts = {}
    for _ in range(n):
        op = pick_op(rng)
        counts[op] = counts.get(op, 0) + 1
        await tb.step(op, rng.getrandbits(32), rng.getrandbits(32))
    await tb.drain()
    groups = {}
    for weight, names in GROUPS:
        groups[names[0] + "..."] = sum(counts.get(OPCODES[x], 0) for x in names)
    tb.finish("test_workload", f" ({n} ops back-to-back, group counts {groups})")
