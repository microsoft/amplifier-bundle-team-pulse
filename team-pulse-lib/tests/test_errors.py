# SPDX-License-Identifier: MIT
"""Tests for team_pulse_lib.errors — typed exception family."""

from __future__ import annotations

import pytest

from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
    TeamPulseError,
)


def test_base_is_exception_subclass() -> None:
    assert issubclass(TeamPulseError, Exception)


@pytest.mark.parametrize(
    "exc_cls",
    [
        TeamPulseAuthError,
        TeamPulseAPIError,
        TeamPulseConnectionError,
    ],
)
def test_subclass_inherits_team_pulse_error(exc_cls: type) -> None:
    assert issubclass(exc_cls, TeamPulseError)


def test_api_error_carries_status_and_body() -> None:
    err = TeamPulseAPIError(status=503, body="upstream down")
    assert err.status == 503
    assert err.body == "upstream down"
    assert "503" in str(err)


def test_api_error_is_raisable() -> None:
    with pytest.raises(TeamPulseAPIError) as exc_info:
        raise TeamPulseAPIError(status=500, body="internal error")
    assert exc_info.value.status == 500
