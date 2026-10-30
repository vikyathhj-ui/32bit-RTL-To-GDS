"""Cross-check model/alu_ref.py against Spike, the RISC-V reference ISA simulator.

For every legal opcode, a seeded set of (a, b) vectors is turned into a
bare-metal RV32 program (li a0,A; li a1,B; <insn> a2,a0,a1; sw a2,0(s0)).
The program runs on `spike --isa=rv32i_zbb`, and the dumped signature is
compared word by word with alu_ref.alu().

RISC-V has no flags and no illegal-opcode output, so this checks `y` only;
flags and illegal opcodes are covered by model/test_alu_ref.py.

Run inside the iic-osic container from the repo root:
    .venv/bin/python model/spike_xcheck.py            # writes results/model_xcheck.json
Exit status is 0 only if every vector matches.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from alu_ref import OPCODES, UNARY_OPS, alu  # noqa: E402

GCC = "riscv64-unknown-elf-gcc"
SPIKE = "spike"
ISA = "rv32i_zbb"

CORNERS = [0, 1, 0xFFFFFFFF, 0x80000000, 0x7FFFFFFF, 0xAAAAAAAA, 0x55555555]
SHIFT_AMOUNTS = [0, 1, 2, 15, 16, 31, 32, 33, 63]

# Assembly mnemonics for each model op name (identical except lower case).
MNEMONIC = {name: name.lower() for name in OPCODES}


def tools_available() -> tuple[bool, str]:
    missing = [t for t in (GCC, SPIKE) if shutil.which(t) is None]
    return (not missing, "missing: " + ", ".join(missing) if missing else "")


def make_vectors(seed: int, n_random: int) -> list[tuple[str, int, int]]:
    rng = random.Random(seed)
    vecs: list[tuple[str, int, int]] = []
    for name in OPCODES:
        if name in UNARY_OPS:
            pairs = [(a, 0) for a in CORNERS]
            pairs += [(1 << i, 0) for i in range(32)]            # every CLZ/CTZ result
            pairs += [((1 << i) - 1, 0) for i in range(33)]
        else:
            pairs = [(a, b) for a in CORNERS for b in CORNERS]
            if name in ("SLL", "SRL", "SRA", "ROL", "ROR"):
                pairs += [(a, s) for a in CORNERS for s in SHIFT_AMOUNTS]
        pairs += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(n_random)]
        vecs += [(name, a, b) for a, b in pairs]
    return vecs


def _s32(x: int) -> int:
    """Signed decimal for `li` so the assembler never sees an out-of-range literal."""
    return x - (1 << 32) if x & 0x80000000 else x


def gen_asm(vecs: list[tuple[str, int, int]]) -> str:
    out = ["    .text", "    .globl run_vectors", "run_vectors:"]
    for name, a, b in vecs:
        out.append(f"    li a0, {_s32(a)}")
        if name in UNARY_OPS:
            out.append(f"    {MNEMONIC[name]} a2, a0")
        else:
            out.append(f"    li a1, {_s32(b)}")
            out.append(f"    {MNEMONIC[name]} a2, a0, a1")
        out.append("    sw a2, 0(s0)")
        out.append("    addi s0, s0, 4")
    out += ["    j done", "",
            "    .data", "    .align 4", "    .globl begin_signature", "begin_signature:",
            f"    .fill {len(vecs)}, 4, 0xdeadbeef",
            "    .globl end_signature", "end_signature:", ""]
    return "\n".join(out)


def run(cmd: list[str], cwd: Path) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}{p.stderr}")
    return p.stdout + p.stderr


def first_line(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip().splitlines()[0] if (p.stdout + p.stderr).strip() else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--random", type=int, default=250, help="random vectors per op")
    ap.add_argument("--build", type=Path, default=REPO / "sim_build" / "spike")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "model_xcheck.json")
    args = ap.parse_args(argv)
    # Tools run with cwd=build dir, so relative paths must be resolved first.
    args.build, args.out = args.build.resolve(), args.out.resolve()

    ok, why = tools_available()
    if not ok:
        print(f"spike_xcheck: cannot run, {why}", file=sys.stderr)
        return 2

    vecs = make_vectors(args.seed, args.random)
    args.build.mkdir(parents=True, exist_ok=True)
    (args.build / "vectors.S").write_text(gen_asm(vecs))
    elf, sig = args.build / "xcheck.elf", args.build / "signature.txt"
    sig.unlink(missing_ok=True)

    gcc_cmd = [GCC, f"-march={ISA}", "-mabi=ilp32", "-nostdlib", "-nostartfiles",
               "-T", str(HERE / "spike" / "link.ld"),
               str(HERE / "spike" / "crt.S"), str(args.build / "vectors.S"), "-o", str(elf)]
    spike_cmd = [SPIKE, f"--isa={ISA}", f"+signature={sig}", "--signature-granularity=4", str(elf)]
    run(gcc_cmd, args.build)
    run(spike_cmd, args.build)

    words = [int(line, 16) for line in sig.read_text().split()]
    if len(words) < len(vecs):
        raise RuntimeError(f"signature has {len(words)} words, expected {len(vecs)}")

    per_op = {name: {"vectors": 0, "mismatches": 0} for name in OPCODES}
    mismatches = []
    for (name, a, b), got in zip(vecs, words):
        exp = alu(OPCODES[name], a, b).y
        per_op[name]["vectors"] += 1
        if got != exp:
            per_op[name]["mismatches"] += 1
            if len(mismatches) < 50:
                mismatches.append({"op": name, "a": f"0x{a:08x}", "b": f"0x{b:08x}",
                                   "spike": f"0x{got:08x}", "model": f"0x{exp:08x}"})

    total_mm = sum(v["mismatches"] for v in per_op.values())
    report = {
        "check": "model/alu_ref.py vs Spike (y only)",
        "result": "PASS" if total_mm == 0 else "FAIL",
        "vectors": len(vecs),
        "mismatches": total_mm,
        "seed": args.seed,
        "random_per_op": args.random,
        "ops_checked": len(per_op),
        "per_op": per_op,
        "first_mismatches": mismatches,
        "tools": {"spike": first_line([SPIKE, "--help"]),
                  "gcc": first_line([GCC, "--version"]), "isa": ISA},
        "commands": {"compile": " ".join(gcc_cmd), "simulate": " ".join(spike_cmd)},
        "source_files": {"signature": str(sig.relative_to(REPO)) if sig.is_relative_to(REPO) else str(sig)},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"spike_xcheck: {report['result']}  {len(vecs)} vectors, {len(per_op)} ops, "
          f"{total_mm} mismatches -> {args.out}")
    for m in mismatches[:10]:
        print("  mismatch:", m)
    return 0 if total_mm == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
