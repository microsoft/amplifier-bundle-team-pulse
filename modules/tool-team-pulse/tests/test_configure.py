# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Configure tool: validate https url, persist via lib config, reset provider."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from amplifier_module_tool_team_pulse.tool import TeamPulseConfigureTool, _ClientProvider


def _provider() -> _ClientProvider:
    return _ClientProvider(build=AsyncMock())


async def test_configure_rejects_non_https(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list = []
    # Match the real 0A signature: save_config(url, api_app_id=None, *, path=None).
    monkeypatch.setattr(
        "amplifier_module_tool_team_pulse.tool.tpl_config.save_config",
        lambda url, api_app_id=None, **k: saved.append(url),
    )
    tool = TeamPulseConfigureTool(_provider())

    result = await tool.execute({"url": "http://insecure.example.com"})

    assert result.success is False
    assert result.error["code"] == "invalid_url"
    assert saved == []  # nothing persisted


async def test_configure_persists_and_resets_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}

    def _fake_save(url, api_app_id=None, *, path=None):
        calls["url"] = url
        calls["api_app_id"] = api_app_id
        return Path("/tmp/team-pulse/config.yaml")

    monkeypatch.setattr("amplifier_module_tool_team_pulse.tool.tpl_config.save_config", _fake_save)
    provider = _provider()
    reset_called = {"n": 0}

    async def _fake_reset() -> None:
        reset_called["n"] += 1

    monkeypatch.setattr(provider, "reset", _fake_reset)
    tool = TeamPulseConfigureTool(provider)

    result = await tool.execute({"url": "https://pulse.example.com", "client_id": "abc"})

    assert result.success is True
    # url is positional; client_id is forwarded as the api_app_id kwarg.
    assert calls["url"] == "https://pulse.example.com"
    assert calls["api_app_id"] == "abc"
    assert reset_called["n"] == 1  # provider reset so next call rebuilds
    assert "https://pulse.example.com" in result.output["saved_url"]


async def test_configure_omits_client_id_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def _fake_save(url, api_app_id=None, *, path=None):
        captured["url"] = url
        captured["api_app_id"] = api_app_id
        return Path("/tmp/x")

    monkeypatch.setattr("amplifier_module_tool_team_pulse.tool.tpl_config.save_config", _fake_save)
    tool = TeamPulseConfigureTool(_provider())

    result = await tool.execute({"url": "https://pulse.example.com"})

    assert result.success is True
    # Absent client_id → api_app_id is None, so the lib preserves any existing on-disk app-id.
    assert captured["api_app_id"] is None


def test_configure_schema_unchanged() -> None:
    schema = TeamPulseConfigureTool(_provider()).input_schema
    assert schema["required"] == ["url"]
    assert "client_id" in schema["properties"]
    assert schema["additionalProperties"] is False
