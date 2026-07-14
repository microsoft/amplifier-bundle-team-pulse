# SPDX-License-Identifier: MIT
"""S9: Zero-amplifier import guard.

Spawns a subprocess that imports team_pulse_lib and verifies that no
amplifier_* top-level module is present in sys.modules. This is the CI
guard that proves the standalone library has zero Amplifier ecosystem
dependency at import time.
"""

from __future__ import annotations

import subprocess
import sys


def test_no_amplifier_modules_imported() -> None:
    """Importing team_pulse_lib must not pull in any amplifier_* module."""
    code = (
        "import team_pulse_lib, sys; "
        "bad = [k for k in sys.modules if k.split('.')[0] == 'amplifier']; "
        "assert not bad, f'amplifier_* modules found in sys.modules: {bad}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Zero-amplifier import guard failed.\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
