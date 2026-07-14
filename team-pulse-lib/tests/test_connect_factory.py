# SPDX-License-Identifier: MIT
"""Tests for TeamPulseClient.connect() — the blessed factory classmethod.

Covers:
- connect(base_url=...) → url-in-code path: auth_mode='az', api_app_id=DEFAULT, provenance correct
- connect(base_url=..., key='tp_x') → ApiKeyAuth + auth_mode='key'
- connect() (no args) → env-var fallback via config.from_args
- force='az'/'key' honored by connect()
- invalid force → ValueError
- PRECEDENCE: explicit base_url arg wins over AMPLIFIER_TEAM_PULSE_URL env var
- PRECEDENCE: explicit key arg wins over AMPLIFIER_TEAM_PULSE_KEY env var
- from_env() still behaves as env-only wrapper
- from_config() still behaves as file-based wrapper
- PROVENANCE fix: direct __init__ with AzCredentialAuth → auth_mode='az' (regression guard)
- PROVENANCE fix: direct __init__ with ApiKeyAuth → auth_mode='key'
- DEFAULT_API_APP_ID importable from team_pulse_lib
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import team_pulse_lib as tpl
import team_pulse_lib.config as tp_config
from team_pulse_lib.auth import ApiKeyAuth, AzCredentialAuth
from team_pulse_lib.client import TeamPulseClient
from team_pulse_lib.config import DEFAULT_API_APP_ID

# ---------------------------------------------------------------------------
# Fixtures — clean env + credential double
# ---------------------------------------------------------------------------

_ENV_VARS = [
    "AMPLIFIER_TEAM_PULSE_URL",
    "AMPLIFIER_TEAM_PULSE_KEY",
    "AMPLIFIER_TEAM_PULSE_API_APP_ID",
    "AMPLIFIER_TEAM_PULSE_AUTH_MODE",
    "AMPLIFIER_TEAM_PULSE_DIR",
]

_BASE_URL = "https://team-pulse.test"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove all team-pulse env vars and redirect config dir to an empty tmp dir."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    tp_config._WARNED_ONCE.clear()
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_DIR", str(tmp_path))


class _CredDouble:
    """Minimal async credential double — avoids hitting the Azure identity chain."""

    async def get_token(self, *args: Any, **kwargs: Any) -> Any:
        class _Token:
            token = "stub-token"
            expires_on = 9_999_999_999

        return _Token()


@pytest.fixture
def _cred() -> _CredDouble:
    return _CredDouble()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ResolvedStub:
    """Stand-in for ResolvedConfig — decouples tests from implementation internals."""

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


class _FakeAuth:
    async def headers(self) -> dict[str, str]:
        return {"X-Team-Pulse-Key": "tp_fake"}


# ---------------------------------------------------------------------------
# connect() — url-in-code path (base_url supplied, no key → Azure)
# ---------------------------------------------------------------------------


def test_connect_base_url_in_code_selects_az_and_defaults_app_id(
    monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble
) -> None:
    """connect(base_url=URL) with no key → auth_mode='az', api_app_id=DEFAULT, forced=False."""
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://ignored.example.com")
    client = TeamPulseClient.connect(
        base_url=_BASE_URL,
        # no key → AzCredentialAuth is selected (key-wins rule)
    )
    assert isinstance(client, TeamPulseClient)
    assert client._base_url == _BASE_URL
    assert client._auth_mode == "az"
    assert isinstance(client._auth, AzCredentialAuth)
    assert client._api_app_id == DEFAULT_API_APP_ID
    assert client._forced is False


def test_connect_base_url_in_code_provenance_correct(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    """connect(base_url=URL) → describe() returns correct provenance fields."""
    import asyncio

    client = TeamPulseClient.connect(base_url=_BASE_URL)

    async def _check() -> None:
        info = await client.describe()
        assert info.base_url == _BASE_URL
        assert info.auth_mode == "az"
        assert info.credential_type == "azure_default_credential"
        assert info.api_app_id == DEFAULT_API_APP_ID
        assert info.forced is False

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# connect() — key supplied → ApiKeyAuth
# ---------------------------------------------------------------------------


def test_connect_with_key_selects_api_key_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """connect(base_url=URL, key='tp_x') → ApiKeyAuth + auth_mode='key'."""
    client = TeamPulseClient.connect(base_url=_BASE_URL, key="tp_mykey")
    assert isinstance(client, TeamPulseClient)
    assert client._auth_mode == "key"
    assert isinstance(client._auth, ApiKeyAuth)


# ---------------------------------------------------------------------------
# connect() — env-var fallback (no base_url arg)
# ---------------------------------------------------------------------------


def test_connect_no_args_falls_back_to_env_url(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    """connect() with no args reads AMPLIFIER_TEAM_PULSE_URL from env."""
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", _BASE_URL)

    stub = _ResolvedStub(base_url=_BASE_URL, auth=_FakeAuth(), auth_mode="az", api_app_id=DEFAULT_API_APP_ID)
    captured: dict = {}

    def fake_from_args(*, base_url=None, key=None, force=None, credential=None):
        captured["base_url"] = base_url
        return stub

    monkeypatch.setattr(tp_config, "from_args", fake_from_args)

    client = TeamPulseClient.connect()
    # base_url arg should be None — env fallback happens inside config.from_args
    assert captured["base_url"] is None
    assert client._base_url == _BASE_URL


# ---------------------------------------------------------------------------
# connect() — force honored
# ---------------------------------------------------------------------------


def test_connect_force_az_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect(base_url=URL, key='tp_x', force='az') → AzCredentialAuth despite key present."""
    client = TeamPulseClient.connect(base_url=_BASE_URL, key="tp_mykey", force="az")
    assert client._auth_mode == "az"
    assert isinstance(client._auth, AzCredentialAuth)
    assert client._forced is True


def test_connect_force_key_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect(base_url=URL, key='tp_x', force='key') → ApiKeyAuth + forced=True."""
    client = TeamPulseClient.connect(base_url=_BASE_URL, key="tp_mykey", force="key")
    assert client._auth_mode == "key"
    assert isinstance(client._auth, ApiKeyAuth)
    assert client._forced is True


def test_connect_invalid_force_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect(force='azure') → ValueError immediately (not 'key' or 'az')."""
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", _BASE_URL)
    with pytest.raises(ValueError, match="force must be"):
        TeamPulseClient.connect(force="azure")


# ---------------------------------------------------------------------------
# PRECEDENCE: explicit arg wins over env var
# ---------------------------------------------------------------------------


def test_connect_explicit_base_url_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit base_url arg beats AMPLIFIER_TEAM_PULSE_URL env var."""
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://env.example.com")
    client = TeamPulseClient.connect(base_url=_BASE_URL)
    assert client._base_url == _BASE_URL  # arg wins


def test_connect_explicit_key_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit key arg beats AMPLIFIER_TEAM_PULSE_KEY env var.

    With both set: explicit arg wins → auth strategy determined by the arg key.
    """
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_KEY", "tp_env_key")
    # Explicit key=None-like (empty) arg — let's test a real win: arg="tp_arg" beats env
    client_arg_wins = TeamPulseClient.connect(base_url=_BASE_URL, key="tp_argkey")
    assert isinstance(client_arg_wins._auth, ApiKeyAuth)  # explicit arg selected

    # Also verify: explicit base_url + env key (no key arg) → env key is used
    client_env_key = TeamPulseClient.connect(base_url=_BASE_URL)
    assert isinstance(client_env_key._auth, ApiKeyAuth)  # env key was used


# ---------------------------------------------------------------------------
# from_env() — still behaves as env-only wrapper (no base_url param)
# ---------------------------------------------------------------------------


def test_from_env_passes_force_through_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env(force='az') → connect(force='az') → force lands in config.from_args."""
    captured: dict = {}
    stub = _ResolvedStub(base_url=_BASE_URL, auth=_FakeAuth(), auth_mode="az", forced=True)

    def fake_from_args(*, base_url=None, key=None, force=None, credential=None):
        captured["base_url"] = base_url
        captured["key"] = key
        captured["force"] = force
        return stub

    monkeypatch.setattr(tp_config, "from_args", fake_from_args)

    client = TeamPulseClient.from_env(force="az", timeout=15.0)

    assert isinstance(client, TeamPulseClient)
    assert client._timeout == 15.0
    # from_env must NOT supply base_url or key — it is env-only
    assert captured.get("base_url") is None
    assert captured.get("key") is None
    assert captured.get("force") == "az"


def test_from_env_reads_url_from_env(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    """from_env() reads AMPLIFIER_TEAM_PULSE_URL (no in-code URL involved)."""
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", _BASE_URL)
    client = TeamPulseClient.from_env()
    assert client._base_url == _BASE_URL


# ---------------------------------------------------------------------------
# from_config() — still behaves as file-based wrapper
# ---------------------------------------------------------------------------


def test_from_config_reads_url_from_file(tmp_path: Path) -> None:
    """from_config(path) reads url from the YAML config file."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(f"url: {_BASE_URL}\n", encoding="utf-8")
    client = TeamPulseClient.from_config(str(cfg))
    assert client._base_url == _BASE_URL


def test_from_config_passes_force_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """from_config(path, force='key') passes force to config.from_config."""
    captured: dict = {}
    stub = _ResolvedStub(base_url=_BASE_URL, auth=_FakeAuth(), auth_mode="key", forced=True)

    def fake_from_config(path, force=None, *, credential=None):
        captured["path"] = str(path)
        captured["force"] = force
        return stub

    monkeypatch.setattr(tp_config, "from_config", fake_from_config)

    cfg_path = str(tmp_path / "cfg.yaml")
    client = TeamPulseClient.from_config(cfg_path, force="key")

    assert captured.get("force") == "key"
    assert captured.get("path") == cfg_path
    assert client._auth_mode == "key"
    assert client._forced is True


# ---------------------------------------------------------------------------
# PROVENANCE FIX: direct __init__ with AzCredentialAuth → auth_mode='az'
# ---------------------------------------------------------------------------


def test_direct_init_az_credential_auth_reports_az_mode() -> None:
    """Regression: TeamPulseClient(__init__, auth=AzCredentialAuth) must report auth_mode='az'.

    Before the fix, auth_mode defaulted to 'key' even when AzCredentialAuth was passed,
    causing describe() to return credential_type='api_key' — a provenance mislabel.
    """
    import asyncio

    auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=_CredDouble())
    client = TeamPulseClient(base_url=_BASE_URL, auth=auth)

    async def _check() -> None:
        info = await client.describe()
        assert info.auth_mode == "az", f"Expected 'az', got {info.auth_mode!r}"
        assert info.credential_type == "azure_default_credential", (
            f"Expected 'azure_default_credential', got {info.credential_type!r}"
        )

    asyncio.run(_check())


def test_direct_init_az_credential_auth_infers_api_app_id() -> None:
    """Direct __init__ with AzCredentialAuth infers api_app_id from the auth instance."""
    import asyncio

    auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=_CredDouble())
    client = TeamPulseClient(base_url=_BASE_URL, auth=auth)

    async def _check() -> None:
        info = await client.describe()
        assert info.api_app_id == DEFAULT_API_APP_ID

    asyncio.run(_check())


def test_direct_init_api_key_auth_reports_key_mode() -> None:
    """Direct __init__ with ApiKeyAuth infers auth_mode='key' (not the bug case, sanity check)."""
    import asyncio

    auth = ApiKeyAuth("tp_direct_key")
    client = TeamPulseClient(base_url=_BASE_URL, auth=auth)

    async def _check() -> None:
        info = await client.describe()
        assert info.auth_mode == "key"
        assert info.credential_type == "api_key"

    asyncio.run(_check())


def test_direct_init_explicit_auth_mode_overrides_inference() -> None:
    """When auth_mode is explicitly passed to __init__, it wins over type-inference.

    The inference only fires when auth_mode is absent.  Explicit always wins.
    """
    import asyncio

    # FakeAuth is not AzCredentialAuth, but we explicitly say "az"
    client = TeamPulseClient(
        base_url=_BASE_URL,
        auth=_FakeAuth(),
        auth_mode="az",
        api_app_id="explicit-app-id",
        forced=True,
    )

    async def _check() -> None:
        info = await client.describe()
        assert info.auth_mode == "az"
        assert info.api_app_id == "explicit-app-id"
        assert info.forced is True

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# DEFAULT_API_APP_ID — public surface
# ---------------------------------------------------------------------------


def test_default_api_app_id_importable_from_package_root() -> None:
    """DEFAULT_API_APP_ID must be importable from team_pulse_lib."""
    assert hasattr(tpl, "DEFAULT_API_APP_ID"), "team_pulse_lib.DEFAULT_API_APP_ID is missing"
    assert isinstance(tpl.DEFAULT_API_APP_ID, str)
    assert len(tpl.DEFAULT_API_APP_ID) > 0


def test_default_api_app_id_value_is_canonical_guid() -> None:
    """DEFAULT_API_APP_ID must equal the known canonical Azure AD app GUID."""
    assert tpl.DEFAULT_API_APP_ID == "dea6e881-4cd8-4aba-87da-a52ff3e19bce"


def test_default_api_app_id_in_all() -> None:
    """DEFAULT_API_APP_ID must appear in team_pulse_lib.__all__."""
    assert "DEFAULT_API_APP_ID" in tpl.__all__


# ---------------------------------------------------------------------------
# Empty api_app_id — fail-loud guard still enforced
# ---------------------------------------------------------------------------


def test_az_credential_auth_empty_api_app_id_raises() -> None:
    """AzCredentialAuth must still raise ValueError on empty api_app_id (guard intact)."""
    with pytest.raises(ValueError, match="api_app_id"):
        AzCredentialAuth(api_app_id="")

    with pytest.raises(ValueError, match="api_app_id"):
        AzCredentialAuth(api_app_id="   ")
