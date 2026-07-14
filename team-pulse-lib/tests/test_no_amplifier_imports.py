# SPDX-License-Identifier: MIT
"""Zero-amplifier import guard — full public-surface variant.

Spawns a fresh subprocess that imports team_pulse_lib *and* explicitly
touches every item in the public surface.  The subprocess then scans
sys.modules for any offenders (module named 'amplifier', or starting
with 'amplifier.' or 'amplifier_') and either raises SystemExit with
the offender list or prints 'CLEAN'.

Running the check in a subprocess ensures that modules already loaded
by the test process itself cannot pollute the result.

This is the CI guard that proves the standalone library carries zero
Amplifier-ecosystem coupling at import time.
"""

from __future__ import annotations

import subprocess
import sys


def test_team_pulse_lib_imports_no_amplifier() -> None:
    """Importing team_pulse_lib and its full public surface must not pull in any amplifier* module."""
    code = "\n".join(
        [
            "import sys",
            "from team_pulse_lib import (",
            "    TeamPulseClient, Question, AnswerUpload, SubmittedAnswer,",
            "    ClientInfo, TeamPulseError",
            ")",
            "offenders = [",
            "    m for m in sys.modules",
            "    if m == 'amplifier' or m.startswith('amplifier.') or m.startswith('amplifier_')",
            "]",
            "if offenders:",
            "    raise SystemExit(f'amplifier* modules found in sys.modules: {offenders}')",
            "print('CLEAN')",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Zero-amplifier import guard FAILED.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    assert "CLEAN" in result.stdout, f"Expected 'CLEAN' in stdout but got: {result.stdout!r}\nstderr: {result.stderr!r}"
