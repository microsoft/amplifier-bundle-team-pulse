# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for the _LensTool adapters (read tools).

Step 2: importing from tool.py verifies ImportError before implementation.
All tool classes (TeamPulseInfoTool, etc.) must be importable after Task 2.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

# Use team_pulse_lib errors for connection error test
from team_pulse_lib.errors import TeamPulseConnectionError

# Step 2: these imports FAIL with ImportError until the classes are added to tool.py
from amplifier_module_tool_team_pulse.tool import (
    _TOOL_CLASSES,
    TeamPulseAskTool,
    TeamPulseGetTool,
    TeamPulseGraphTool,
    TeamPulseInfoTool,
    TeamPulsePrefixTool,
    TeamPulseResourcesTool,
    TeamPulseSearchTool,
    TeamPulseWhoamiTool,
)

# ---------------------------------------------------------------------------
# Stub: old-style TeamPulseAPIError with .envelope (duck-typed by _error_result)
# ---------------------------------------------------------------------------


class _APIError(Exception):
    """Minimal stub for the removed amplifier_module_tool_team_pulse.client.TeamPulseAPIError.

    _error_result() in tool.py duck-types on ``.envelope`` being a dict —
    any exception carrying that attribute is passed through verbatim.
    """

    def __init__(self, envelope: dict) -> None:
        self.envelope = envelope
        super().__init__(str(envelope))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(mock_client: AsyncMock) -> MagicMock:
    """Return a mock provider whose async .client() returns mock_client."""
    provider = MagicMock()
    provider.client = AsyncMock(return_value=mock_client)
    return provider


def _client() -> AsyncMock:
    """Return a fresh AsyncMock simulating a TeamPulseClient."""
    return AsyncMock()


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


async def test_info_wraps_lib_info_success() -> None:
    """info: success=True, output equals the dict returned by client.info()."""
    mock_client = _client()
    mock_client.info.return_value = {"name": "team-pulse", "version": "1.0.0"}
    provider = _make_provider(mock_client)

    tool = TeamPulseInfoTool(provider)
    result = await tool.execute({})

    assert result.success is True
    assert result.output == {"name": "team-pulse", "version": "1.0.0"}
    mock_client.info.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------


async def test_resources_forwards_type_and_collection() -> None:
    """resources: forwards type and collection keyword args to client.resources()."""
    mock_client = _client()
    mock_client.resources.return_value = {"count": 0, "resources": []}
    provider = _make_provider(mock_client)

    tool = TeamPulseResourcesTool(provider)
    result = await tool.execute({"type": "project", "collection": "docs"})

    assert result.success is True
    mock_client.resources.assert_awaited_once_with(type="project", collection="docs")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


async def test_search_forwards_q_limit_collection() -> None:
    """search: forwards q, limit, collection to client.search()."""
    mock_client = _client()
    mock_client.search.return_value = {"count": 1, "resources": [{"id": "members/alice"}]}
    provider = _make_provider(mock_client)

    tool = TeamPulseSearchTool(provider)
    result = await tool.execute({"q": "alice", "limit": 10, "collection": "docs"})

    assert result.success is True
    mock_client.search.assert_awaited_once_with(q="alice", limit=10, collection="docs")


async def test_search_collection_none_when_absent() -> None:
    """search: collection=None when not in input (never omitted from call)."""
    mock_client = _client()
    mock_client.search.return_value = {"count": 0, "resources": []}
    provider = _make_provider(mock_client)

    tool = TeamPulseSearchTool(provider)
    await tool.execute({"q": "bob"})

    mock_client.search.assert_awaited_once_with(q="bob", limit=50, collection=None)


# ---------------------------------------------------------------------------
# prefix
# ---------------------------------------------------------------------------


async def test_prefix_forwards_positional_prefix() -> None:
    """prefix: forwards prefix as the positional argument to client.prefix()."""
    mock_client = _client()
    mock_client.prefix.return_value = {"count": 2, "resources": []}
    provider = _make_provider(mock_client)

    tool = TeamPulsePrefixTool(provider)
    result = await tool.execute({"prefix": "projects"})

    assert result.success is True
    mock_client.prefix.assert_awaited_once_with("projects")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_forwards_positional_id() -> None:
    """get: forwards id as the positional argument to client.get()."""
    mock_client = _client()
    mock_client.get.return_value = {"id": "projects/tp", "title": "TP", "type": "project"}
    provider = _make_provider(mock_client)

    tool = TeamPulseGetTool(provider)
    result = await tool.execute({"id": "projects/tp"})

    assert result.success is True
    mock_client.get.assert_awaited_once_with("projects/tp")


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


async def test_graph_calls_graph() -> None:
    """graph: calls client.graph() with no arguments."""
    mock_client = _client()
    mock_client.graph.return_value = {"team": {}, "projects": [], "members": []}
    provider = _make_provider(mock_client)

    tool = TeamPulseGraphTool(provider)
    result = await tool.execute({})

    assert result.success is True
    mock_client.graph.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# whoami
# ---------------------------------------------------------------------------


async def test_whoami_returns_output() -> None:
    """whoami: success=True, output equals identity dict from client.whoami()."""
    identity = {"handle": "alice", "member_id": "members/alice", "auth_method": "key"}
    mock_client = _client()
    mock_client.whoami.return_value = identity
    provider = _make_provider(mock_client)

    tool = TeamPulseWhoamiTool(provider)
    result = await tool.execute({})

    assert result.success is True
    assert result.output == identity


# ---------------------------------------------------------------------------
# ask
# ---------------------------------------------------------------------------


async def test_ask_forwards_prompt_and_focus() -> None:
    """ask: forwards prompt and focus keyword args to client.ask()."""
    mock_client = _client()
    mock_client.ask.return_value = {"content": "The team is doing great.", "prompt_used": "how?"}
    provider = _make_provider(mock_client)

    tool = TeamPulseAskTool(provider)
    result = await tool.execute({"prompt": "how?", "focus": "projects/tp"})

    assert result.success is True
    mock_client.ask.assert_awaited_once_with(prompt="how?", focus="projects/tp")


# ---------------------------------------------------------------------------
# Error handling: TeamPulseAPIError (old-style with .envelope)
# ---------------------------------------------------------------------------


async def test_api_error_returns_envelope() -> None:
    """TeamPulseAPIError: success=False, error code/status taken from exc.envelope."""
    envelope = {"code": "not_found", "message": "resource not found", "status": 404}
    mock_client = _client()
    mock_client.info.side_effect = _APIError(envelope)
    provider = _make_provider(mock_client)

    tool = TeamPulseInfoTool(provider)
    result = await tool.execute({})

    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "not_found"
    assert result.error["status"] == 404


# ---------------------------------------------------------------------------
# Error handling: TeamPulseConnectionError
# ---------------------------------------------------------------------------


async def test_connection_error_returns_transport_error() -> None:
    """TeamPulseConnectionError: code='transport_error', message contains 'dns boom'."""
    mock_client = _client()
    mock_client.info.side_effect = TeamPulseConnectionError("dns boom: could not resolve host")
    provider = _make_provider(mock_client)

    tool = TeamPulseInfoTool(provider)
    result = await tool.execute({})

    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "transport_error"
    assert "dns boom" in result.error["message"]


# ---------------------------------------------------------------------------
# Names and schemas
# ---------------------------------------------------------------------------


def test_info_name() -> None:
    """info tool: name is 'team_pulse_info'."""
    tool = TeamPulseInfoTool(_client())
    assert tool.name == "team_pulse_info"


def test_resources_name() -> None:
    """resources tool: name is 'team_pulse_resources'."""
    tool = TeamPulseResourcesTool(_client())
    assert tool.name == "team_pulse_resources"


def test_search_schema_additional_properties_false() -> None:
    """search tool: input_schema has additionalProperties=False."""
    tool = TeamPulseSearchTool(_client())
    assert tool.input_schema.get("additionalProperties") is False


def test_search_schema_required_is_q() -> None:
    """search tool: required field set is exactly {'q'}."""
    tool = TeamPulseSearchTool(_client())
    assert set(tool.input_schema.get("required", [])) == {"q"}


# ---------------------------------------------------------------------------
# ask — name, schema, description guards (ported from test_ask.py / test_ask_guidance.py)
# ---------------------------------------------------------------------------


def test_ask_tool_name() -> None:
    """ask tool: name is 'team_pulse_ask'."""
    tool = TeamPulseAskTool(None)
    assert tool.name == "team_pulse_ask"


def test_ask_tool_input_schema_prompt_required_focus_optional() -> None:
    """ask tool: prompt is required; focus is optional; additionalProperties=False."""
    tool = TeamPulseAskTool(None)
    schema = tool.input_schema
    assert schema["required"] == ["prompt"]
    assert "focus" in schema["properties"]
    assert "focus" not in schema["required"]
    assert schema.get("additionalProperties") is False


def test_ask_tool_in_tool_classes() -> None:
    """ask tool: TeamPulseAskTool is in _TOOL_CLASSES."""
    assert TeamPulseAskTool in _TOOL_CLASSES


def test_ask_tool_description_prefers_read_tools() -> None:
    """Guard: description must steer agent toward read tools by default."""
    tool = TeamPulseAskTool(None)
    assert "PREFER THE READ TOOLS" in tool.description


def test_ask_tool_description_explicit_invocation_only() -> None:
    """Guard: description must mark ask as explicit-invocation-only."""
    tool = TeamPulseAskTool(None)
    assert "ONLY when the user explicitly" in tool.description


# ---------------------------------------------------------------------------
# resources/search schema — collection & view guards (ported from test_collections.py)
# ---------------------------------------------------------------------------


def test_resources_tool_schema_has_collection_property() -> None:
    """resources tool: input_schema must expose a 'collection' string property."""
    tool = TeamPulseResourcesTool(None)
    schema = tool.input_schema
    assert "collection" in schema["properties"]
    assert schema["properties"]["collection"]["type"] == "string"


def test_resources_tool_schema_has_no_view_property() -> None:
    """resources tool: input_schema must NOT contain a 'view' property (removed as dead param)."""
    tool = TeamPulseResourcesTool(None)
    assert "view" not in tool.input_schema["properties"]


def test_search_tool_schema_has_collection_property() -> None:
    """search tool: input_schema must expose a 'collection' string property."""
    tool = TeamPulseSearchTool(None)
    schema = tool.input_schema
    assert "collection" in schema["properties"]
    assert schema["properties"]["collection"]["type"] == "string"
