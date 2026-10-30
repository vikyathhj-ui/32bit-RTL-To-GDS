"""Runs the Spike cross-check (model/spike_xcheck.py) as part of pytest.

Skips, with the reason shown, where Spike or the RISC-V GCC is not installed
(e.g. plain CI runners). Inside the iic-osic container it always runs.
"""

import json

import pytest

import spike_xcheck


def test_spike_xcheck(tmp_path):
    ok, why = spike_xcheck.tools_available()
    if not ok:
        pytest.skip(f"Spike cross-check not run: {why}")
    out = tmp_path / "xcheck.json"
    rc = spike_xcheck.main(["--build", str(tmp_path / "build"), "--out", str(out)])
    report = json.loads(out.read_text())
    assert rc == 0 and report["mismatches"] == 0, report["first_mismatches"][:5]
    assert report["ops_checked"] == 27
