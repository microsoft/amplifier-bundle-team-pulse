# SPDX-License-Identifier: MIT
"""Typed exception family for team_pulse_lib.

This library RAISES these exceptions; callers catch them directly.
The shim catches them and re-maps to amplifier_* error types.

Auth failures carry an actionable message explaining what the caller must do
(e.g. set TEAM_PULSE_API_KEY, or ensure `az login` has been run).
"""

from __future__ import annotations


class TeamPulseError(Exception):
    """Base class for all team_pulse_lib errors."""


class TeamPulseAuthError(TeamPulseError):
    """Credential acquisition failed, or the server returned HTTP 401/403."""


class TeamPulseAPIError(TeamPulseError):
    """Any non-2xx response that is not an auth failure.

    Carries the HTTP status code and the decoded response body so callers can
    inspect or log them without re-parsing the raw bytes.
    """

    def __init__(self, *, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Team Pulse API error {status}: {body}")


class TeamPulseConnectionError(TeamPulseError):
    """Transport-level failure (DNS resolution, connection refused, timeout)."""
