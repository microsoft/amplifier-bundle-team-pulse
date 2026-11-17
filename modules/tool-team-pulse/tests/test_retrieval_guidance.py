# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Guidance regressions at the mounted surface and real offline client boundary.

The synthetic HTTP fixtures test adapter compatibility, not server routing or
agent compliance. Prompt checks inspect the mode's actual contributed sources;
they do not claim a host/model trial of the compressed descriptions.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import respx
import yaml
from team_pulse_lib import TeamPulseClient

from amplifier_module_tool_team_pulse.tool import TeamPulseReadTool, mount

ROOT = Path(__file__).resolve().parents[3]
BASE_URL = "https://lens-guidance.test"


async def _mounted():
    coordinator = SimpleNamespace(mount=AsyncMock())
    await mount(coordinator, {})
    return {call.kwargs["name"]: call.args[1] for call in coordinator.mount.await_args_list}


def _without_descriptions(value):
    if isinstance(value, dict):
        return {key: _without_descriptions(item) for key, item in value.items() if key != "description"}
    if isinstance(value, list):
        return [_without_descriptions(item) for item in value]
    return value


async def test_mounted_read_contract_and_dispatch_are_unchanged():
    tool = (await _mounted())["team_pulse_read"]
    assert _without_descriptions(tool.input_schema) == {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": ["get", "search", "prefix", "resources", "info", "whoami", "status"]},
            "id": {"type": "string"},
            "q": {"type": "string", "minLength": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            "prefix": {"type": "string"},
            "type": {"type": "string"},
            "collection": {"type": "string"},
            "status": {"type": "string", "enum": ["active", "archived", "all"]},
        },
        "required": ["op"],
        "additionalProperties": False,
    }
    assert {op: (cls.__name__, required) for op, (cls, required) in tool._OPS.items()} == {
        "get": ("TeamPulseGetTool", ("id",)),
        "search": ("TeamPulseSearchTool", ("q",)),
        "prefix": ("TeamPulsePrefixTool", ("prefix",)),
        "resources": ("TeamPulseResourcesTool", ()),
        "info": ("TeamPulseInfoTool", ()),
        "whoami": ("TeamPulseWhoamiTool", ()),
        "status": ("TeamPulseStatusTool", ()),
    }


async def test_write_and_ask_rendered_definitions_are_unchanged():
    # Full rendered definitions at published main d7e29f12, including descriptions.
    expected = {
        "team_pulse_write": "fe6d41faf7acafc68cc8970df7362d998939a3f7ecd4c7533f80b7b377a90fc4",
        "team_pulse_ask": "390d2d368b803229d6ee9c5a7b2d704ffc4b1ba8b37a4af8c692cebaf6ad28fb",
    }
    tools = await _mounted()
    for name, digest in expected.items():
        tool = tools[name]
        rendered = {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        assert hashlib.sha256(json.dumps(rendered, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == digest


async def test_bootstrap_and_field_distinctions_reach_the_actual_mount():
    tool = (await _mounted())["team_pulse_read"]
    assert "when unfamiliar" in tool.description
    assert "read selected IDs before document-backed answers" in tool.description
    assert "snippets are pointers" in tool.description
    assert "separate calls across collections" in tool.description
    fields = tool.input_schema["properties"]
    assert "exact returned resource ID, not a directory" in fields["id"]["description"]
    assert "path boundary" in fields["prefix"]["description"]
    assert "one info.collections[].name, never a subtree" in fields["collection"]["description"]
    assert "not all collections" in fields["collection"]["description"]


class _OfflineAuth:
    async def headers(self):
        return {}


@pytest.mark.parametrize("guide", [None, {}, {"search": {"matching": "fixture"}, "unknown": [1, {"nested": True}]}])
async def test_info_roundtrips_old_and_additive_unknown_fields_through_mounted_handler(guide):
    payload = {
        "name": "fixture",
        "resource_types": ["member", "question"],
        "collections": [{"name": "renamed-flat"}],
        "unknown_top_level": {"future": ["kept"]},
    }
    if guide is not None:
        payload["usage_guide"] = {
            **guide,
            "scope": {"collection": "one registered name"},
            "examples": [{"query": {"collection": "<collections[].name>"}}],
            "client_boundary": "HTTP reference, not permission",
        }
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/api/lens/info").respond(200, json=payload)
        async with TeamPulseClient(base_url=BASE_URL, auth=_OfflineAuth()) as client:
            tools = await _mounted()
            # Keep the actual mounted dispatcher/InfoTool; replace only its lazy
            # provider with the real offline client, never client.info or _call.
            tools["team_pulse_read"]._handlers["info"]._client = client
            result = await tools["team_pulse_read"].execute({"op": "info"})
    assert result.success
    assert result.output == payload
    assert route.call_count == 1


@pytest.mark.parametrize("names", [("atlas", "folio"), ("decisions-renamed", "repo-renamed")])
async def test_discovered_collections_full_prefix_and_exact_get_forward_without_invented_args(names):
    first, flat = names
    prefix = f"{first}/scope"
    page_id = f"{prefix}/decision.md"
    sibling_id = f"{first}/scope-archive/old.md"
    catalog = {
        "resource_types": [],
        "collections": [
            {"name": first, "sub_corpora": [
                {"name": prefix, "summary": "current decisions"},
                {"name": f"{first}/scope-archive", "summary": "archive"},
            ]},
            {"name": flat},
        ],
    }
    stub = {"id": page_id, "title": "Decision", "type": "corpus", "snippet": "a pointer"}
    sibling = {"id": sibling_id, "title": "Old", "type": "corpus"}
    # Metadata intentionally larger than the returned page: this exposes the
    # current normalizer's loss, not a fixture that blesses exhaustive coverage.
    listing = {"resources": [stub], "count": 1, "total": 12, "query": "migration", "filters_applied": {"x": True}}
    document = {
        "id": page_id, "content": "The inspected decision.",
        "content_revision": "fixture-r1", "truncated": True, "next_offset": 99,
    }
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/api/lens/info").respond(200, json=catalog)
        first_search = router.get(
            f"{BASE_URL}/api/lens/resources/search",
            params={"q": "migration", "collection": first, "limit": 20},
        ).respond(200, json={**listing, "resources": [stub, sibling], "count": 2})
        second_search = router.get(
            f"{BASE_URL}/api/lens/resources/search",
            params={"q": "migration", "collection": flat, "limit": 20},
        ).respond(200, json={"count": 0, "resources": []})
        browse = router.get(f"{BASE_URL}/api/lens/resources/prefix/{prefix}").respond(200, json=listing)
        get = router.get(f"{BASE_URL}/api/lens/resources/{page_id}").respond(200, json=document)
        async with TeamPulseClient(base_url=BASE_URL, auth=_OfflineAuth()) as client:
            tool = TeamPulseReadTool(client)
            info = await tool.execute({"op": "info"})
            searches = [
                await tool.execute({"op": "search", "q": "migration", "collection": collection["name"], "limit": 20})
                for collection in info.output["collections"]
            ]
            discovered_prefix = info.output["collections"][0]["sub_corpora"][0]["name"]
            result = await tool.execute({"op": "prefix", "prefix": discovered_prefix})
            selected_id = result.output["resources"][0]["id"]
            evidence = await tool.execute({"op": "get", "id": selected_id})
    assert searches[0].success and searches[1].success and result.success and evidence.success
    assert searches[0].output == {"resources": [stub, sibling], "count": 2}
    assert result.output == {"resources": [stub], "count": 1}
    assert evidence.output == document  # truncation/revision survive, not continuations
    assert first_search.call_count == second_search.call_count == browse.call_count == get.call_count == 1
    assert all(set(call.request.url.params) == {"q", "collection", "limit"} for call in (first_search.calls[0], second_search.calls[0]))
    assert not browse.calls[0].request.url.query
    assert not get.calls[0].request.url.query


async def test_unknown_collection_is_failure_not_empty_evidence_and_discovery_can_refresh():
    with respx.mock(assert_all_called=True) as router:
        router.get(f"{BASE_URL}/api/lens/resources/search").respond(
            404, json={"error": {"code": "unknown_collection", "message": "retired collection", "status": 404}},
        )
        router.get(f"{BASE_URL}/api/lens/info").respond(200, json={"collections": [{"name": "replacement"}]})
        async with TeamPulseClient(base_url=BASE_URL, auth=_OfflineAuth()) as client:
            tool = TeamPulseReadTool(client)
            result = await tool.execute({"op": "search", "q": "topic", "collection": "retired"})
            refreshed = await tool.execute({"op": "info"})
    assert result.success is False
    assert result.error["status"] == 404
    assert "unknown_collection" in result.error["message"]
    assert refreshed.output["collections"][0]["name"] == "replacement"


async def test_omitted_collection_is_really_omitted_not_expanded_to_a_union():
    with respx.mock(assert_all_called=True) as router:
        route = router.get(f"{BASE_URL}/api/lens/resources/search").respond(200, json={"count": 0, "resources": []})
        async with TeamPulseClient(base_url=BASE_URL, auth=_OfflineAuth()) as client:
            result = await TeamPulseReadTool(client).execute({"op": "search", "q": "topic"})
    assert result.success
    assert dict(route.calls[0].request.url.params) == {"q": "topic", "limit": "50"}


def _prompt_sources():
    return [ROOT / "context/corpus-retrieval.md", ROOT / "context/using-team-pulse.md", ROOT / "modes/team-pulse.md"]


def test_mode_contributes_the_canonical_reference_without_always_on_context_or_policy_changes():
    behavior = yaml.safe_load((ROOT / "behaviors/team-pulse.yaml").read_text())
    # Only an unindented delimiter closes frontmatter; the agent instruction
    # contains its own indented Markdown separator.
    frontmatter = (ROOT / "modes/team-pulse.md").read_text().removeprefix("---\n").split("\n---\n", 1)[0]
    mode = yaml.safe_load(frontmatter)["mode"]
    assert behavior["context"]["include"] == []
    assert mode["contributes"]["context"] == [
        "@team-pulse:context/using-team-pulse.md", "@team-pulse:context/corpus-retrieval.md",
    ]
    expert = mode["contributes"]["agents"]["team-pulse-expert"]
    assert expert["model_role"] == ["fast", "general"]
    assert "@team-pulse:context/corpus-retrieval.md" in expert["instruction"]
    assert mode["default_action"] == "allow"
    assert mode["tools"]["safe"] == ["team_pulse_read", "team_pulse_write", "team_pulse_ask", "delegate"]
    assert "read-only retrieval expert" in expert["instruction"]
    assert "EXPLICIT-USE ONLY" in expert["instruction"]
    assert "Never mix with raw reads in one answer" in expert["instruction"]


def test_prompt_read_examples_use_only_current_callable_arguments_and_discovered_collections():
    allowed = {
        "info": set(), "whoami": set(), "status": set(),
        "get": {"id"}, "prefix": {"prefix"}, "resources": {"type", "collection", "status"},
        "search": {"q", "limit", "collection"},
    }
    calls = []
    for path in _prompt_sources():
        text = path.read_text()
        assert not re.search(r"""collection\s*=\s*["'](?:corpus|docs|[^"']*/[^"']*)["']""", text), path
        assert "targets the sub-corpus you mean" not in text
        assert "page with `limit`/`offset`" not in text
        for example in re.findall(r"```python\n(.*?)```", text, re.S):
            for call in ast.walk(ast.parse(example)):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "team_pulse_read":
                    continue
                args = {keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords}
                assert set(args) - {"op"} <= allowed[args["op"]], (path, args)
                if "collection" in args:
                    assert args["collection"].startswith("<"), (path, args)
                calls.append(args)
    assert {call["op"] for call in calls} >= {"info", "search", "prefix", "get", "resources"}


def test_canonical_workflow_names_evidence_authority_date_and_client_limits():
    text = (ROOT / "context/corpus-retrieval.md").read_text()
    for guard in (
        "not every call needs discovery", "not another registered collection",
        "not all collections", "not host policy or permission", "older server without a guide",
        "no document continuation or listing pagination arguments", "drops `total`, `query` and `filters_applied`",
        "not proof of exhaustive coverage", "not the event date", "Snippets are pointers",
        "get` and inspect **both** sides",
    ):
        assert guard in text, guard