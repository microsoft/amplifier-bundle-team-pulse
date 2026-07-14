# SPDX-License-Identifier: MIT
"""Tests for team_pulse_lib.auth — AuthStrategy protocol, is_valid_key, and ApiKeyAuth."""

from __future__ import annotations

import pytest

from team_pulse_lib.auth import ApiKeyAuth, is_valid_key
from team_pulse_lib.errors import TeamPulseAuthError

# ---------------------------------------------------------------------------
# is_valid_key — N1 rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key, expected",
    [
        ("tp_secret", True),
        ("  tp_secret  ", True),  # strips before checking prefix
        ("", False),
        ("   ", False),  # whitespace-only
        (None, False),
        ("nope", False),  # no tp_ prefix
        ("TP_UPPER", False),  # wrong case
    ],
)
def test_is_valid_key(key: str | None, expected: bool) -> None:
    assert is_valid_key(key) == expected


# ---------------------------------------------------------------------------
# ApiKeyAuth — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apikey_auth_emits_correct_header() -> None:
    auth = ApiKeyAuth("tp_secret")
    headers = await auth.headers()
    assert headers == {"X-Team-Pulse-Key": "tp_secret"}


@pytest.mark.asyncio
async def test_apikey_auth_strips_surrounding_whitespace() -> None:
    auth = ApiKeyAuth("  tp_secret  ")
    headers = await auth.headers()
    assert headers == {"X-Team-Pulse-Key": "tp_secret"}


# ---------------------------------------------------------------------------
# ApiKeyAuth — rejection at construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_key",
    [
        "",
        "   ",
        "nope",
        None,
    ],
)
def test_apikey_auth_rejects_invalid_key(bad_key: str | None) -> None:
    with pytest.raises(TeamPulseAuthError):
        ApiKeyAuth(bad_key)
