# SPDX-License-Identifier: MIT
"""Tests for team_pulse_lib.config — settings resolution and client_id alias deprecation."""

from __future__ import annotations

from pathlib import Path

import pytest

from team_pulse_lib import config
from team_pulse_lib.config import (
    DEFAULT_API_APP_ID,
    _load_yaml,
    _resolve_settings,
)

# ---------------------------------------------------------------------------
# Fixture: clean env + deprecation-guard state before every test
# ---------------------------------------------------------------------------

_ENV_VARS = [
    "AMPLIFIER_TEAM_PULSE_URL",
    "AMPLIFIER_TEAM_PULSE_KEY",
    "AMPLIFIER_TEAM_PULSE_API_APP_ID",
    "AMPLIFIER_TEAM_PULSE_AUTH_MODE",
    "AMPLIFIER_TEAM_PULSE_DIR",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config._WARNED_ONCE.clear()


# ---------------------------------------------------------------------------
# base_url resolution
# ---------------------------------------------------------------------------


def test_env_url_wins_over_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://env.example.com")
    s = _resolve_settings({"url": "https://file.example.com"})
    assert s.base_url == "https://env.example.com"


def test_file_url_used_when_env_absent() -> None:
    s = _resolve_settings({"url": "https://file.example.com"})
    assert s.base_url == "https://file.example.com"


# ---------------------------------------------------------------------------
# api_app_id resolution
# ---------------------------------------------------------------------------


def test_api_app_id_defaults_to_default() -> None:
    s = _resolve_settings({})
    assert s.api_app_id == DEFAULT_API_APP_ID


def test_api_app_id_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_API_APP_ID", "custom-app-id")
    s = _resolve_settings({})
    assert s.api_app_id == "custom-app-id"


def test_client_id_alias_honored_with_deprecation_warning() -> None:
    with pytest.warns(DeprecationWarning):
        s = _resolve_settings({"client_id": "alias-app-id"})
    assert s.api_app_id == "alias-app-id"


def test_api_app_id_prefers_new_key_over_alias() -> None:
    # client_id present but api_app_id takes precedence — no warning emitted
    s = _resolve_settings({"api_app_id": "real-app-id", "client_id": "alias-app-id"})
    assert s.api_app_id == "real-app-id"


# ---------------------------------------------------------------------------
# api_key resolution
# ---------------------------------------------------------------------------


def test_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_KEY", "tp_envkey")
    s = _resolve_settings({})
    assert s.api_key == "tp_envkey"


def test_key_from_file_when_env_absent() -> None:
    s = _resolve_settings({"key": "tp_filekey"})
    assert s.api_key == "tp_filekey"


# ---------------------------------------------------------------------------
# legacy_auth_mode resolution
# ---------------------------------------------------------------------------


def test_legacy_auth_mode_captured_from_file() -> None:
    s = _resolve_settings({"auth_mode": "key"})
    assert s.legacy_auth_mode == "key"


# ---------------------------------------------------------------------------
# _load_yaml
# ---------------------------------------------------------------------------


def test_load_yaml_returns_empty_dict_for_missing_file(tmp_path: Path) -> None:
    result = _load_yaml(tmp_path / "nonexistent.yaml")
    assert result == {}
