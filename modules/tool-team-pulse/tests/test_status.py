# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for TeamPulseStatusTool.

Verifies that the tool:
- Has name 'team_pulse_status'
- Has a closed empty input schema ({}, additionalProperties: False)
- Awaits client.describe() and returns an explicit allow-list of ClientInfo fields
- Never leaks secrets (no key/api_key/token/access_token/authorization/secret keys)
- repr has no 'tp_' or 'Bearer ' substrings

Step 2 of TDD verifies ImportError: cannot import name 'TeamPulseStatusTool' before
the class is added to tool.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from team_pulse_lib import ClientInfo
from team_pulse_lib import TeamPulseClient as _LibClient

from amplifier_module_tool_team_pulse import TeamPulseStatusTool

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_BASE_URL = "https://team-pulse.example.com"
_API_APP_ID = "dea6e881-4cd8-4aba-87da-a52ff3e19bce"

# ClientInfo for az-mode tests (matches acceptance criteria values exactly)
_CLIENT_INFO_AZ = ClientInfo(
    base_url=_BASE_URL,
    auth_mode="az",
    api_app_id=_API_APP_ID,
    credential_type="azure_default_credential",
    forced=False,
    resolved=True,
    az_identity_hint="samuel@microsoft.com",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(*, info: ClientInfo = _CLIENT_INFO_AZ) -> AsyncMock:
    """Return AsyncMock(spec=_LibClient) with describe() returning info.

    Using spec=_LibClient prevents AsyncMock from auto-creating a callable
    .client attribute, which would cause execute() to treat the mock as a
    _ClientProvider and resolve a nested mock instead of the direct client.
    """
    mock = AsyncMock(spec=_LibClient)
    mock.describe.return_value = info
    return mock


# ---------------------------------------------------------------------------
# Scenario 1: Tool metadata
# ---------------------------------------------------------------------------


def test_tool_name() -> None:
    """Tool name must be 'team_pulse_status'."""
    tool = TeamPulseStatusTool(AsyncMock(spec=_LibClient))
    assert tool.name == "team_pulse_status"


def test_schema_properties_is_empty() -> None:
    """input_schema['properties'] must be {} (closed empty object)."""
    tool = TeamPulseStatusTool(AsyncMock(spec=_LibClient))
    assert tool.input_schema["properties"] == {}


def test_schema_additional_properties_false() -> None:
    """input_schema['additionalProperties'] must be False."""
    tool = TeamPulseStatusTool(AsyncMock(spec=_LibClient))
    assert tool.input_schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Scenario 2: Returns all ClientInfo fields (az mode, acceptance criteria values)
# ---------------------------------------------------------------------------


async def test_status_returns_base_url() -> None:
    """Output must include base_url from ClientInfo."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.success is True
    assert result.output["base_url"] == _BASE_URL


async def test_status_returns_auth_mode_az() -> None:
    """Output must include auth_mode='az'."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.output["auth_mode"] == "az"


async def test_status_returns_api_app_id() -> None:
    """Output must include api_app_id."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.output["api_app_id"] == _API_APP_ID


async def test_status_returns_credential_type() -> None:
    """Output must include credential_type='azure_default_credential'."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.output["credential_type"] == "azure_default_credential"


async def test_status_returns_forced_false() -> None:
    """Output must include forced=False."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.output["forced"] is False


async def test_status_returns_resolved_true() -> None:
    """Output must include resolved=True."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.output["resolved"] is True


async def test_status_output_has_no_server_supports_metadata() -> None:
    """server_supports_metadata is gone — it must not appear in the status output."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert "server_supports_metadata" not in result.output


async def test_describe_awaited_once() -> None:
    """client.describe() must be awaited exactly once per execute() call."""
    mock = _make_mock_client()
    tool = TeamPulseStatusTool(mock)
    await tool.execute({})
    mock.describe.assert_awaited_once()


# ---------------------------------------------------------------------------
# Scenario 3: Never leaks secrets
# ---------------------------------------------------------------------------

_SECRET_KEYS = {"key", "api_key", "token", "access_token", "authorization", "secret"}


async def test_output_has_no_secret_keys() -> None:
    """Output dict must not contain any secret-bearing keys."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.success is True
    for forbidden in _SECRET_KEYS:
        assert forbidden not in result.output, f"output must not contain secret key '{forbidden}'"


async def test_repr_has_no_tp_prefix() -> None:
    """repr(output) must not contain 'tp_' (API-key value prefix)."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert "tp_" not in repr(result.output)


async def test_repr_has_no_bearer() -> None:
    """repr(output) must not contain 'Bearer ' (auth-header value prefix)."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert "Bearer " not in repr(result.output)


# ---------------------------------------------------------------------------
# Scenario 4: az account az_identity_hint (display-only, from bundle.md fix 4)
# ---------------------------------------------------------------------------


async def test_status_returns_az_identity_hint_in_az_mode() -> None:
    """Output must include az_identity_hint when the underlying ClientInfo carries one."""
    tool = TeamPulseStatusTool(_make_mock_client())
    result = await tool.execute({})
    assert result.output["az_identity_hint"] == "samuel@microsoft.com"


async def test_status_returns_az_identity_hint_none_in_key_mode() -> None:
    """Output's az_identity_hint must be None when ClientInfo carries none (key mode)."""
    key_info = ClientInfo(
        base_url=_BASE_URL,
        auth_mode="key",
        api_app_id=None,
        credential_type="api_key",
        forced=False,
        resolved=True,
    )
    tool = TeamPulseStatusTool(_make_mock_client(info=key_info))
    result = await tool.execute({})
    assert result.output["az_identity_hint"] is None
