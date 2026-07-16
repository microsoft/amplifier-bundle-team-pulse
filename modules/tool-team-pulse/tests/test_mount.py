# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for provider-backed mount() — Task 6.

Verifies the new mount() contract:
  - configure tool is always first
  - mounts configure + all _DATA_TOOL_CLASSES (10 data tools)
  - all 10 expected names present, including team_pulse_status
  - all tools share one provider object (single id)
  - mount bridges settings into env, then calls TeamPulseClient.from_env(force=None)
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from team_pulse_lib import TeamPulseClient

from amplifier_module_tool_team_pulse.tool import (
    _DATA_TOOL_CLASSES,
    TeamPulseConfigureTool,
    mount,
)


class _FakeCoordinator:
    """Minimal stand-in for the Amplifier coordinator mount surface."""

    def __init__(self) -> None:
        self.mounted: list[tuple[str, Any, str]] = []

    async def mount(self, kind: str, tool: Any, name: str) -> None:
        self.mounted.append((kind, tool, name))


# ---------------------------------------------------------------------------
# Test 1: configure tool always first
# ---------------------------------------------------------------------------


async def test_configure_tool_always_first() -> None:
    """mounted[0] is 'team_pulse_configure' and an instance of TeamPulseConfigureTool."""
    coord = _FakeCoordinator()
    await mount(coord, {})
    assert coord.mounted[0][2] == "team_pulse_configure"
    assert isinstance(coord.mounted[0][1], TeamPulseConfigureTool)


# ---------------------------------------------------------------------------
# Test 2: mounts configure + all data tools
# ---------------------------------------------------------------------------


async def test_mounts_configure_plus_all_data_tools() -> None:
    """Total mounted == 1 (configure) + len(_DATA_TOOL_CLASSES)."""
    coord = _FakeCoordinator()
    await mount(coord, {})
    assert len(coord.mounted) == 1 + len(_DATA_TOOL_CLASSES)


# ---------------------------------------------------------------------------
# Test 3: all 10 expected names present including team_pulse_status
# ---------------------------------------------------------------------------

_EXPECTED_NAMES = {
    "team_pulse_configure",
    "team_pulse_info",
    "team_pulse_whoami",
    "team_pulse_resources",
    "team_pulse_search",
    "team_pulse_prefix",
    "team_pulse_get",
    "team_pulse_graph",
    "team_pulse_download_corpus",
    "team_pulse_download_answers",
    "team_pulse_submit_answer",
    "team_pulse_ask",
    "team_pulse_status",
}


async def test_all_expected_names_present_including_status() -> None:
    """All tool names are mounted, including the two bulk download tools."""
    coord = _FakeCoordinator()
    await mount(coord, {})
    names = {name for _, _, name in coord.mounted}
    assert names == _EXPECTED_NAMES


# ---------------------------------------------------------------------------
# Test 4: all tools share one provider (single id)
# ---------------------------------------------------------------------------


async def test_all_tools_share_one_provider() -> None:
    """Configure tool and all data tools reference the exact same provider object."""
    coord = _FakeCoordinator()
    await mount(coord, {})

    # Configure tool stores the provider as _provider
    configure_provider = coord.mounted[0][1]._provider  # noqa: SLF001

    # Data tools store the shared provider as _client (legacy attr name in _LensTool)
    for _, tool, name in coord.mounted[1:]:
        assert tool._client is configure_provider, (  # noqa: SLF001
            f"{name}: expected shared provider (id={id(configure_provider)}), got id={id(tool._client)}"  # noqa: SLF001
        )


# ---------------------------------------------------------------------------
# Test 5: mount bridges settings into env then calls from_env(force=None)
# ---------------------------------------------------------------------------


async def test_mount_bridges_settings_to_env_and_calls_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_make_build sets env vars from config, then calls TeamPulseClient.from_env(force=None).

    config keys to env var mapping verified:
      url         -> AMPLIFIER_TEAM_PULSE_URL
      key         -> AMPLIFIER_TEAM_PULSE_KEY
      client_id   -> AMPLIFIER_TEAM_PULSE_API_APP_ID  (alias — same target as api_app_id)
      auth_mode   -> AMPLIFIER_TEAM_PULSE_AUTH_MODE
    force must be None (lib owns all inference).
    """
    # Clear relevant env vars so pre-existing values don't contaminate the snapshot
    for env_var in (
        "AMPLIFIER_TEAM_PULSE_URL",
        "AMPLIFIER_TEAM_PULSE_KEY",
        "AMPLIFIER_TEAM_PULSE_API_APP_ID",
        "AMPLIFIER_TEAM_PULSE_AUTH_MODE",
    ):
        monkeypatch.delenv(env_var, raising=False)

    captured: dict[str, Any] = {}

    class _FakeClient:
        """Minimal async-context-manager stub returned by the monkeypatched from_env."""

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

    def _fake_from_env(*, force: str | None = None, timeout: float = 30.0) -> _FakeClient:
        # Snapshot the env state at the moment from_env is invoked (inside _build)
        captured["url"] = os.environ.get("AMPLIFIER_TEAM_PULSE_URL")
        captured["key"] = os.environ.get("AMPLIFIER_TEAM_PULSE_KEY")
        captured["api_app_id"] = os.environ.get("AMPLIFIER_TEAM_PULSE_API_APP_ID")
        captured["auth_mode"] = os.environ.get("AMPLIFIER_TEAM_PULSE_AUTH_MODE")
        captured["force"] = force
        return _FakeClient()

    monkeypatch.setattr(TeamPulseClient, "from_env", _fake_from_env)

    config = {
        "url": "https://x.example.com",
        "key": "tp_k",
        "client_id": "cid",  # aliases to AMPLIFIER_TEAM_PULSE_API_APP_ID
        "auth_mode": "key",
    }

    coord = _FakeCoordinator()
    await mount(coord, config)

    # Trigger the lazy build by awaiting the shared provider
    provider = coord.mounted[0][1]._provider  # noqa: SLF001
    await provider.client()

    assert captured["url"] == "https://x.example.com"
    assert captured["key"] == "tp_k"
    assert captured["api_app_id"] == "cid"  # from client_id alias
    assert captured["auth_mode"] == "key"
    assert captured["force"] is None
