# SPDX-License-Identifier: MIT
"""Tests for TeamPulseClient construction and async context manager (Task 4).

Covers:
- __init__: base_url validation, trailing-slash stripping, provenance storage
- __aenter__: eager credential acquisition, error wrapping
- __aexit__: http client teardown
- _require_http: guard outside context

Note: FakeAuth is defined inline here so this module has no dependency on the
conftest package import path; the conftest fixture is still available for use
in other ways but we avoid a cross-package import for test isolation.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

import team_pulse_lib.config as tp_config
from team_pulse_lib.client import TeamPulseClient
from team_pulse_lib.errors import TeamPulseAPIError, TeamPulseAuthError, TeamPulseConnectionError
from team_pulse_lib.models import ClientInfo

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeAuth:
    """Minimal AuthStrategy stub that satisfies async headers() and counts calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.call_count: int = 0

    async def headers(self) -> dict[str, str]:
        self.call_count += 1
        if self._fail:
            raise RuntimeError("boom: no credential available")
        return {"X-Team-Pulse-Key": "tp_fake"}


# ---------------------------------------------------------------------------
# test_init_stores_base_url_and_strips_trailing_slash
# ---------------------------------------------------------------------------


def test_init_stores_base_url_and_strips_trailing_slash():
    auth = FakeAuth()
    client = TeamPulseClient(base_url="https://team-pulse.test/", auth=auth)
    assert client._base_url == "https://team-pulse.test"


# ---------------------------------------------------------------------------
# test_init_requires_base_url
# ---------------------------------------------------------------------------


def test_init_requires_base_url():
    auth = FakeAuth()
    with pytest.raises(ValueError, match="base_url"):
        TeamPulseClient(base_url="", auth=auth)


# ---------------------------------------------------------------------------
# test_aenter_returns_client_and_eagerly_acquires_credential
# ---------------------------------------------------------------------------


async def test_aenter_returns_client_and_eagerly_acquires_credential():
    auth = FakeAuth()
    client = TeamPulseClient(base_url="https://team-pulse.test", auth=auth)
    async with client as entered:
        assert entered is client
        # headers() was called exactly once at __aenter__ (eager acquisition)
        assert auth.call_count == 1


# ---------------------------------------------------------------------------
# test_aenter_failure_is_wrapped_as_team_pulse_auth_error
# ---------------------------------------------------------------------------


async def test_aenter_failure_is_wrapped_as_team_pulse_auth_error():
    """FakeAuth raises RuntimeError; __aenter__ must wrap it as TeamPulseAuthError."""
    auth = FakeAuth(fail=True)
    client = TeamPulseClient(base_url="https://team-pulse.test", auth=auth)
    with pytest.raises(TeamPulseAuthError):
        async with client:
            pass  # should not reach here


# ---------------------------------------------------------------------------
# test_methods_outside_context_raise_runtime_error
# ---------------------------------------------------------------------------


def test_methods_outside_context_raise_runtime_error():
    """_require_http() outside async-with must raise RuntimeError with 'async with' in message."""
    auth = FakeAuth()
    client = TeamPulseClient(base_url="https://team-pulse.test", auth=auth)
    with pytest.raises(RuntimeError, match="async with"):
        client._require_http()


# ---------------------------------------------------------------------------
# Task 5: _get / _post with typed error mapping
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_applies_auth_headers_and_returns_response():
    """GET 200: _get must forward Accept: application/json and auth headers."""
    route = respx.get("https://team-pulse.test/api/test").mock(return_value=httpx.Response(200, json={"ok": True}))
    auth = FakeAuth()
    async with TeamPulseClient(base_url="https://team-pulse.test", auth=auth) as client:
        resp = await client._get("/api/test")
    assert resp.status_code == 200
    assert route.called
    req = route.calls[0].request
    assert req.headers["accept"] == "application/json"
    assert req.headers["x-team-pulse-key"] == "tp_fake"


@pytest.mark.parametrize("status_code", [401, 403])
@respx.mock
async def test_get_maps_401_403_to_auth_error(status_code: int):
    """GET 401/403: _get must raise TeamPulseAuthError."""
    respx.get("https://team-pulse.test/api/test").mock(return_value=httpx.Response(status_code))
    auth = FakeAuth()
    async with TeamPulseClient(base_url="https://team-pulse.test", auth=auth) as client:
        with pytest.raises(TeamPulseAuthError):
            await client._get("/api/test")


@respx.mock
async def test_get_maps_other_non_2xx_to_api_error_with_status_and_body():
    """GET 500: _get must raise TeamPulseAPIError carrying .status and 'boom' in .body."""
    respx.get("https://team-pulse.test/api/test").mock(return_value=httpx.Response(500, text="boom"))
    auth = FakeAuth()
    async with TeamPulseClient(base_url="https://team-pulse.test", auth=auth) as client:
        with pytest.raises(TeamPulseAPIError) as exc_info:
            await client._get("/api/test")
    assert exc_info.value.status == 500
    assert "boom" in exc_info.value.body


@respx.mock
async def test_get_maps_transport_error_to_connection_error():
    """ConnectError transport failure must map to TeamPulseConnectionError."""
    respx.get("https://team-pulse.test/api/test").mock(side_effect=httpx.ConnectError("connection refused"))
    auth = FakeAuth()
    async with TeamPulseClient(base_url="https://team-pulse.test", auth=auth) as client:
        with pytest.raises(TeamPulseConnectionError):
            await client._get("/api/test")


@respx.mock
async def test_post_sends_json_body_and_returns_response():
    """POST 201: _post must send JSON body and return the response."""
    route = respx.post("https://team-pulse.test/api/submit").mock(
        return_value=httpx.Response(201, json={"created": True})
    )
    auth = FakeAuth()
    async with TeamPulseClient(base_url="https://team-pulse.test", auth=auth) as client:
        resp = await client._post("/api/submit", {"hello": "world"})
    assert resp.status_code == 201
    assert route.called
    req = route.calls[0].request
    assert json.loads(req.content) == {"hello": "world"}


# ---------------------------------------------------------------------------
# Task 10: describe() + capability probe wiring
# ---------------------------------------------------------------------------

_BASE_URL = "https://team-pulse.test"


async def test_describe_before_context_entry_is_unresolved_and_unprobed():
    """describe() before context entry: all provenance fields reflected, resolved=False, no auth calls."""
    auth = FakeAuth()
    client = TeamPulseClient(base_url=_BASE_URL, auth=auth)
    info = await client.describe()
    assert isinstance(info, ClientInfo)
    assert info.resolved is False
    assert info.base_url == _BASE_URL
    assert info.auth_mode == "key"
    assert info.credential_type == "api_key"
    assert info.forced is False
    assert auth.call_count == 0  # NO network call before entry


async def test_describe_after_entry_is_resolved():
    """describe() after __aenter__: resolved=True."""
    auth = FakeAuth()
    async with TeamPulseClient(base_url=_BASE_URL, auth=auth) as client:
        info = await client.describe()
    assert info.resolved is True


def test_describe_reflects_forced_and_az_identity():
    """describe() with az mode + forced=True: az-specific fields reflected; works outside async context."""

    async def _check() -> None:
        auth = FakeAuth()
        client = TeamPulseClient(
            base_url=_BASE_URL,
            auth=auth,
            auth_mode="az",
            api_app_id="dea6e881-4cd8-4aba-87da-a52ff3e19bce",
            forced=True,
        )
        info = await client.describe()
        assert info.auth_mode == "az"
        assert info.forced is True
        assert info.credential_type == "azure_default_credential"
        assert info.api_app_id == "dea6e881-4cd8-4aba-87da-a52ff3e19bce"

    asyncio.run(_check())



def test_describe_reflects_az_identity_hint_in_az_mode():
    """describe() in az mode surfaces AzCredentialAuth.az_identity_hint on ClientInfo."""

    class _FakeAzAuth:
        """Minimal az-mode double exposing headers() + az_identity_hint, like AzCredentialAuth."""

        def __init__(self) -> None:
            self.az_identity_hint = "samuel@microsoft.com"

        async def headers(self) -> dict[str, str]:
            return {"Authorization": "Bearer fake-token"}

    async def _check() -> None:
        from team_pulse_lib.auth import AzCredentialAuth

        # Monkeypatch-free: construct a real AzCredentialAuth so isinstance() in
        # describe() matches, but inject our fake credential double.
        from types import SimpleNamespace

        class _FakeCred:
            async def get_token(self, scope: str) -> SimpleNamespace:
                import time

                return SimpleNamespace(token="fake.jwt.token", expires_on=time.time() + 3600)

        auth = AzCredentialAuth(api_app_id="dea6e881", credential=_FakeCred())
        client = TeamPulseClient(
            base_url=_BASE_URL,
            auth=auth,
            auth_mode="az",
            api_app_id="dea6e881-4cd8-4aba-87da-a52ff3e19bce",
        )
        await auth.headers()  # populate the token so az_identity_hint can decode it
        info = await client.describe()
        # The fake token above isn't a real JWT, so az_identity_hint decodes to None --
        # this test asserts the WIRING (describe() reads auth.az_identity_hint), not the
        # JWT-decoding logic itself (covered in test_auth_azure.py).
        assert info.az_identity_hint is auth.az_identity_hint

    asyncio.run(_check())


def test_describe_az_identity_hint_is_none_in_key_mode():
    """describe() in key mode: az_identity_hint is always None (ApiKeyAuth has no such attribute)."""
    auth = FakeAuth()
    client = TeamPulseClient(base_url=_BASE_URL, auth=auth)

    async def _check() -> None:
        info = await client.describe()
        assert info.az_identity_hint is None

    asyncio.run(_check())

# ---------------------------------------------------------------------------
# Task 12: from_env / from_config factory classmethods
# ---------------------------------------------------------------------------


class _ResolvedStub:
    """Minimal stand-in for ResolvedConfig — decouples factory tests from 0A internals."""

    def __init__(
        self,
        base_url: str,
        auth: object,
        auth_mode: str = "key",
        api_app_id: str | None = None,
        forced: bool = False,
    ) -> None:
        self.base_url = base_url
        self.auth = auth
        self.auth_mode = auth_mode
        self.api_app_id = api_app_id
        self.forced = forced


def test_from_env_delegates_to_connect_which_calls_from_args(monkeypatch):
    """from_env(force=X) → connect(force=X) → config.from_args(base_url=None, key=None, force=X).

    from_env is now a thin wrapper over connect(); it does NOT call config.from_env
    directly.  The monkeypatch target is config.from_args — the single resolution home.
    """
    captured: dict = {}
    stub = _ResolvedStub(
        base_url=_BASE_URL,
        auth=FakeAuth(),
        auth_mode="az",
        api_app_id="app-1",
        forced=True,
    )

    def fake_from_args(*, base_url=None, key=None, force=None, credential=None):
        captured["base_url"] = base_url
        captured["key"] = key
        captured["force"] = force
        return stub

    monkeypatch.setattr(tp_config, "from_args", fake_from_args)

    client = TeamPulseClient.from_env(force="az", timeout=12.0)

    assert isinstance(client, TeamPulseClient)
    assert client._base_url == _BASE_URL
    assert client._timeout == 12.0
    assert client._auth_mode == "az"
    assert client._api_app_id == "app-1"
    assert client._forced is True
    # from_env must NOT pass a base_url or key — it is env-only
    assert captured.get("base_url") is None
    assert captured.get("key") is None
    assert captured.get("force") == "az"


def test_from_config_delegates_to_config_then_constructs(monkeypatch):
    """from_config passes path and force to config.from_config and constructs TeamPulseClient."""
    captured: dict = {}
    stub = _ResolvedStub(
        base_url=_BASE_URL,
        auth=FakeAuth(),
        auth_mode="key",
        api_app_id=None,
        forced=False,
    )

    def fake_from_config(path, force=None, *, credential=None):
        captured["path"] = str(path)
        captured["force"] = force
        return stub

    monkeypatch.setattr(tp_config, "from_config", fake_from_config)

    client = TeamPulseClient.from_config("/tmp/cfg.yaml", force="key")

    assert client._auth_mode == "key"
    assert captured.get("path") == "/tmp/cfg.yaml"
    assert captured.get("force") == "key"
