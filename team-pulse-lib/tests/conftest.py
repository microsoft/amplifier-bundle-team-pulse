# SPDX-License-Identifier: MIT
"""Shared test fixtures for team-pulse-lib Phase 0B tests.

Provides FakeAuth (AuthStrategy stub), Clock (controllable monotonic clock),
and the answer_factory fixture.  These keep 0B tests fully decoupled from
the concrete auth strategies in team_pulse_lib.auth.
"""

from __future__ import annotations

from typing import Any

import pytest

from team_pulse_lib.models import AnswerUpload

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

BASE_URL: str = "https://team-pulse.test"


# ---------------------------------------------------------------------------
# FakeAuth — minimal AuthStrategy stub for 0B tests
# ---------------------------------------------------------------------------


class FakeAuth:
    """Minimal AuthStrategy stub that satisfies async headers() and counts calls.

    Carries NO provenance — provenance comes from ResolvedConfig via factories,
    not from auth strategies themselves.

    Args:
        fail: When True, headers() raises RuntimeError('boom: no credential available').
        header_value: Custom value for the X-Team-Pulse-Key header.
                      Defaults to 'tp_fake' when None.
    """

    def __init__(self, *, fail: bool = False, header_value: str | None = None) -> None:
        self._fail = fail
        self._header_value = header_value if header_value is not None else "tp_fake"
        self.call_count: int = 0

    async def headers(self) -> dict[str, str]:
        self.call_count += 1
        if self._fail:
            raise RuntimeError("boom: no credential available")
        return {"X-Team-Pulse-Key": self._header_value}


# ---------------------------------------------------------------------------
# Clock — controllable monotonic clock for time-sensitive tests
# ---------------------------------------------------------------------------


class Clock:
    """Controllable monotonic clock for deterministic time-dependent tests.

    Args:
        start: Initial clock value in seconds (default 1000.0).

    Usage::

        clock = Clock()
        assert clock() == 1000.0
        clock.advance(30)
        assert clock() == 1030.0
    """

    def __init__(self, start: float = 1000.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_url() -> str:
    """Base URL for the fake Team Pulse server."""
    return BASE_URL


@pytest.fixture
def fake_auth() -> FakeAuth:
    """A default (non-failing) FakeAuth instance."""
    return FakeAuth()


@pytest.fixture
def answer_factory():
    """Factory fixture that builds AnswerUpload with sensible defaults.

    Override any field by passing keyword arguments::

        def test_something(answer_factory):
            upload = answer_factory(user_id='alice', answer='my answer')
    """

    def _factory(
        *,
        question_id: str = "effective-practices",
        user_id: str = "",
        answer: str = "an answer",
        generated_at: str = "2026-06-25T17:00:00Z",
        metadata: dict[str, Any] | None = None,
    ) -> AnswerUpload:
        return AnswerUpload(
            question_id=question_id,
            user_id=user_id,
            answer=answer,
            generated_at=generated_at,
            metadata=metadata if metadata is not None else {"source_session_ids": ["s1"]},
        )

    return _factory
