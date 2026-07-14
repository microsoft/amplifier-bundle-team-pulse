# SPDX-License-Identifier: MIT
"""Tests for team_pulse_lib.auth — AzCredentialAuth and _build_credential."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from team_pulse_lib.auth import AzCredentialAuth, _build_credential
from team_pulse_lib.errors import TeamPulseAuthError

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeCred:
    """Async credential double that records get_token calls."""

    def __init__(self, token: str = "fake-token", expires_in: float = 3600.0) -> None:
        self._token = token
        self._expires_in = expires_in
        self.calls: int = 0
        self.scopes: list[str] = []

    async def get_token(self, scope: str) -> SimpleNamespace:
        self.calls += 1
        self.scopes.append(scope)
        return SimpleNamespace(token=self._token, expires_on=time.time() + self._expires_in)


class _FailCred:
    """Async credential double that always raises RuntimeError."""

    async def get_token(self, scope: str) -> SimpleNamespace:  # noqa: ARG002
        raise RuntimeError("no credential configured")


# ---------------------------------------------------------------------------
# AzCredentialAuth — emits correct header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_az_credential_auth_emits_bearer_header() -> None:
    auth = AzCredentialAuth(api_app_id="dea6e881", credential=_FakeCred())
    headers = await auth.headers()
    assert headers == {"Authorization": "Bearer fake-token"}


# ---------------------------------------------------------------------------
# AzCredentialAuth — requests correct scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_az_credential_auth_requests_correct_scope() -> None:
    cred = _FakeCred()
    auth = AzCredentialAuth(api_app_id="dea6e881", credential=cred)
    await auth.headers()
    assert cred.scopes == ["api://dea6e881/.default"]


# ---------------------------------------------------------------------------
# AzCredentialAuth — token cached within TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_az_credential_auth_token_cached_within_ttl() -> None:
    """Second call within TTL must NOT re-acquire (calls == 1)."""
    cred = _FakeCred(expires_in=3600.0)  # expires in 1 hour, well beyond 300s skew
    auth = AzCredentialAuth(api_app_id="dea6e881", credential=cred)
    await auth.headers()
    await auth.headers()
    assert cred.calls == 1


# ---------------------------------------------------------------------------
# AzCredentialAuth — refetches when near expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_az_credential_auth_refetches_when_near_expiry() -> None:
    """Token expiring in 100s is within the 300s skew window — must be refetched."""
    cred = _FakeCred(expires_in=100.0)  # 100s < 300s skew → stale immediately
    auth = AzCredentialAuth(api_app_id="dea6e881", credential=cred)
    await auth.headers()
    await auth.headers()
    assert cred.calls == 2


# ---------------------------------------------------------------------------
# AzCredentialAuth — credential failure wrapped as TeamPulseAuthError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_az_credential_auth_wraps_failure_as_auth_error() -> None:
    auth = AzCredentialAuth(api_app_id="dea6e881", credential=_FailCred())
    with pytest.raises(TeamPulseAuthError) as exc_info:
        await auth.headers()
    assert "credential" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# _build_credential — factory behaviour
# ---------------------------------------------------------------------------


def test_build_credential_returns_injected_sentinel() -> None:
    sentinel = object()
    result = _build_credential(sentinel)
    assert result is sentinel


def test_build_credential_constructs_default_when_none() -> None:
    """_build_credential(None) must construct a real DefaultAzureCredential (no network)."""
    result = _build_credential(None)
    assert result is not None
    # Verify it is actually a DefaultAzureCredential instance (lazy, no network call)
    from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

    assert isinstance(result, DefaultAzureCredential)
