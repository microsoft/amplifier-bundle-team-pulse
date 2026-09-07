# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Dispatch behaviour of team_pulse_read / team_pulse_write.

Covers what the op enum newly makes possible to get wrong: an unknown op, a
missing per-op required argument (which the JSON schema cannot express, since
`required` is conditional on `op`), and the op key leaking through to the
handler.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from amplifier_module_tool_team_pulse.tool import (
    TeamPulseReadTool,
    TeamPulseWriteTool,
)


def _provider(client: AsyncMock) -> MagicMock:
    provider = MagicMock()
    provider.client = AsyncMock(return_value=client)
    return provider


def _client() -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value={"id": "members/jdoe"})
    client.search = AsyncMock(return_value={"resources": [], "count": 0})
    client.prefix = AsyncMock(return_value={"resources": [], "count": 0})
    client.resources = AsyncMock(return_value={"resources": [], "count": 0})
    client.graph = AsyncMock(return_value={"nodes": []})
    client.info = AsyncMock(return_value={"name": "team-pulse"})
    client.whoami = AsyncMock(return_value={"handle": "jdoe"})
    client.download_corpus = AsyncMock(return_value={"written": 3})
    return client


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


async def test_read_get_routes_to_client_get() -> None:
    client = _client()
    tool = TeamPulseReadTool(_provider(client))

    result = await tool.execute({"op": "get", "id": "members/jdoe"})

    assert result.success is True
    client.get.assert_awaited_once_with("members/jdoe")


async def test_read_search_forwards_limit_and_collection() -> None:
    client = _client()
    tool = TeamPulseReadTool(_provider(client))

    await tool.execute({"op": "search", "q": "pulse", "limit": 5, "collection": "docs"})

    client.search.assert_awaited_once_with(q="pulse", limit=5, collection="docs")


async def test_read_resources_forwards_status_filter() -> None:
    client = _client()
    tool = TeamPulseReadTool(_provider(client))

    await tool.execute({"op": "resources", "type": "question", "status": "all"})

    client.resources.assert_awaited_once_with(type="question", collection=None, status="all")


async def test_read_status_op_does_not_collide_with_status_param() -> None:
    """`op='status'` is the client-config read; `status=` is the question filter."""
    client = _client()
    client.describe = AsyncMock(
        return_value=MagicMock(
            base_url="https://x",
            auth_mode="az",
            api_app_id="a",
            credential_type="c",
            forced=None,
            resolved="r",
            az_identity_hint=None,
        )
    )
    tool = TeamPulseReadTool(_provider(client))

    result = await tool.execute({"op": "status"})

    assert result.success is True
    assert result.output["base_url"] == "https://x"
    client.resources.assert_not_awaited()


async def test_write_download_corpus_routes_and_forwards() -> None:
    client = _client()
    tool = TeamPulseWriteTool(_provider(client))

    await tool.execute({"op": "download_corpus", "dest_dir": "/tmp/x", "folder": "handbook"})

    client.download_corpus.assert_awaited_once_with(dest_dir="/tmp/x", folder="handbook")


async def test_op_key_is_not_forwarded_to_the_handler() -> None:
    """The handler must never see `op` — it is dispatcher-only."""
    client = _client()
    tool = TeamPulseReadTool(_provider(client))

    await tool.execute({"op": "prefix", "prefix": "projects"})

    client.prefix.assert_awaited_once_with("projects")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_unknown_op_is_a_named_invalid_argument() -> None:
    tool = TeamPulseReadTool(_provider(_client()))

    result = await tool.execute({"op": "nope"})

    assert result.success is False
    assert result.error["code"] == "invalid_argument"
    assert "nope" in result.error["message"]
    assert "search" in result.error["message"]  # lists the valid ops


async def test_missing_op_is_rejected() -> None:
    tool = TeamPulseReadTool(_provider(_client()))

    result = await tool.execute({"id": "members/jdoe"})

    assert result.success is False
    assert result.error["code"] == "invalid_argument"


async def test_missing_required_arg_names_the_field_not_a_keyerror() -> None:
    tool = TeamPulseReadTool(_provider(_client()))

    result = await tool.execute({"op": "get"})

    assert result.success is False
    assert result.error["code"] == "invalid_argument"
    assert "id" in result.error["message"]


async def test_submit_answer_missing_fields_are_all_named_at_once() -> None:
    tool = TeamPulseWriteTool(_provider(_client()))

    result = await tool.execute({"op": "submit_answer", "user_id": "jdoe"})

    assert result.success is False
    message = result.error["message"]
    for field in ("question_id", "answer", "generated_at"):
        assert field in message
    assert "user_id" not in message


async def test_ops_share_one_provider_instance() -> None:
    """Every op handler holds the same provider, so the client cache is shared."""
    provider = _provider(_client())
    tool = TeamPulseReadTool(provider)

    handlers = list(tool._handlers.values())  # noqa: SLF001
    assert handlers
    assert all(getattr(h, "_client", None) is provider for h in handlers)  # noqa: SLF001
