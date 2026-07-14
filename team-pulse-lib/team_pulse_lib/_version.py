# SPDX-License-Identifier: MIT
"""Single source of truth for the team-pulse-lib version.

This value is read by both the library (team_pulse_lib) and the Amplifier bundle
shim (Phase 0C). Library and shim MUST move in lockstep — a version bump here
must be accompanied by a matching pin in the shim's dependency declaration.
"""

__version__ = "0.1.0"
