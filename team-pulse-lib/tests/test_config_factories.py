# SPDX-License-Identifier: MIT
"""Tests for team_pulse_lib.config — strategy selection, force, legacy migration, factories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from team_pulse_lib import config
from team_pulse_lib.auth import ApiKeyAuth, AzCredentialAuth
from team_pulse_lib.config import ResolvedConfig, from_config, from_env

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ENV_VARS = [
    "AMPLIFIER_TEAM_PULSE_URL",
    "AMPLIFIER_TEAM_PULSE_KEY",
    "AMPLIFIER_TEAM_PULSE_API_APP_ID",
    "AMPLIFIER_TEAM_PULSE_AUTH_MODE",
    "AMPLIFIER_TEAM_PULSE_DIR",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove all team-pulse env vars, clear the deprecation guard, and redirect
    the config dir to an empty tmp dir so the developer's real config is never read."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config._WARNED_ONCE.clear()
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_DIR", str(tmp_path))


class _CredDouble:
    """Minimal async credential stub — lets AzCredentialAuth be constructed
    without hitting the Azure identity chain during tests."""

    async def get_token(self, *args: Any, **kwargs: Any) -> Any:
        class _Token:
            token = "stub-token"
            expires_on = 9999999999

        return _Token()


@pytest.fixture
def _cred() -> _CredDouble:
    return _CredDouble()


# ---------------------------------------------------------------------------
# Key-wins inference
# ---------------------------------------------------------------------------


def test_valid_key_selects_api_key_auth(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_KEY", "tp_secret")
    rc = from_env(credential=_cred)
    assert isinstance(rc, ResolvedConfig)
    assert isinstance(rc.auth, ApiKeyAuth)
    assert rc.auth_mode == "key"
    assert rc.forced is False
    # The secret key must never appear in repr
    assert "tp_secret" not in repr(rc)


def test_no_key_falls_back_to_azure(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
    rc = from_env(credential=_cred)
    assert isinstance(rc.auth, AzCredentialAuth)
    assert rc.auth_mode == "az"
    assert rc.forced is False


@pytest.mark.parametrize("bad_key", ["   ", "nope", "TP_UPPER"])
def test_malformed_key_falls_back_to_az(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble, bad_key: str) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_KEY", bad_key)
    rc = from_env(credential=_cred)
    assert isinstance(rc.auth, AzCredentialAuth)
    assert rc.auth_mode == "az"


# ---------------------------------------------------------------------------
# Force override
# ---------------------------------------------------------------------------


def test_force_key_pins(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_KEY", "tp_secret")
    rc = from_env(force="key", credential=_cred)
    assert isinstance(rc.auth, ApiKeyAuth)
    assert rc.auth_mode == "key"
    assert rc.forced is True


def test_force_az_overrides_present_key(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_KEY", "tp_secret")
    rc = from_env(force="az", credential=_cred)
    assert isinstance(rc.auth, AzCredentialAuth)
    assert rc.auth_mode == "az"
    assert rc.forced is True


@pytest.mark.parametrize("bad_force", ["KEY", "azure", "keyy", "0"])
def test_invalid_force_raises_value_error(monkeypatch: pytest.MonkeyPatch, _cred: _CredDouble, bad_force: str) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
    with pytest.raises(ValueError, match="force must be"):
        from_env(force=bad_force, credential=_cred)


# ---------------------------------------------------------------------------
# Legacy auth_mode migration
# ---------------------------------------------------------------------------


def test_legacy_auth_mode_az_honored(tmp_path: Path, _cred: _CredDouble) -> None:
    # _clean_env already set AMPLIFIER_TEAM_PULSE_DIR=str(tmp_path)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("url: https://api.example.com\nauth_mode: az\n")
    with pytest.warns(DeprecationWarning):
        rc = from_env(credential=_cred)
    assert rc.auth_mode == "az"
    assert rc.forced is True


def test_legacy_auth_mode_invalid_raises(tmp_path: Path, _cred: _CredDouble) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("url: https://api.example.com\nauth_mode: azure\n")
    with pytest.raises(ValueError, match="auth_mode must be"):
        from_env(credential=_cred)


# ---------------------------------------------------------------------------
# Missing base_url
# ---------------------------------------------------------------------------


def test_missing_base_url_raises(_cred: _CredDouble) -> None:
    # No URL in env and empty config dir (set by _clean_env)
    with pytest.raises(ValueError, match="base_url is required"):
        from_env(credential=_cred)


# ---------------------------------------------------------------------------
# from_config with existing file format
# ---------------------------------------------------------------------------


def test_from_config_reads_file_format(tmp_path: Path, _cred: _CredDouble) -> None:
    config_file = tmp_path / "custom.yaml"
    config_file.write_text("url: https://file.example.com\nclient_id: my-app-id\n")
    with pytest.warns(DeprecationWarning):
        rc = from_config(str(config_file), credential=_cred)
    assert rc.base_url == "https://file.example.com"
    assert rc.api_app_id == "my-app-id"
