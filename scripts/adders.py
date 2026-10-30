"""Adder architecture names (BRIEF A2) and their integer ADDER codes.

The RTL parameter ADDER is an integer (rtl/alu_pkg.sv ADDER_*, DECISIONS
D-012); every script and flow config uses the names below and converts with
code(). scripts/check_opcodes.py verifies this table against alu_pkg.sv.
"""

ADDERS = {
    "RCA": 0,
    "CLA4": 1,
    "CSLA": 2,
    "BK": 3,
    "KS": 4,
    "SK": 5,
    "HC": 6,
    "BEH": 7,
}


def code(name: str) -> int:
    return ADDERS[name.upper()]
