# SPDX-License-Identifier: MIT
"""Tests for TeamPulseClient generic lens reads (Task 6).

Covers:
- info: GET /api/lens/info returns body, sends auth header
- resources: query param forwarding, envelope normalisation
- get: fetches resource by ID, requires non-empty ID
- whoami: GET /api/lens/me
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest
import respx

from team_pulse_lib.client import TeamPulseClient
from team_pulse_lib.errors import TeamPulseAPIError

# ---------------------------------------------------------------------------
# Shared test double
# ---------------------------------------------------------------------------

BASE_URL = "https://team-pulse.test"


class FakeAuth:
    """Minimal AuthStrategy stub — always succeeds and injects X-Team-Pulse-Key."""

    async def headers(self) -> dict[str, str]:
        return {"X-Team-Pulse-Key": "tp_fake"}


# ---------------------------------------------------------------------------
# test_info_returns_body_and_sends_auth_header
# ---------------------------------------------------------------------------


@respx.mock
async def test_info_returns_body_and_sends_auth_header():
    """GET /api/lens/info must return body AND forward the auth header."""
    route = respx.get(f"{BASE_URL}/api/lens/info").mock(return_value=httpx.Response(200, json={"version": "1.0"}))
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        body = await client.info()

    assert route.called
    assert body == {"version": "1.0"}
    req = route.calls[0].request
    assert req.headers["x-team-pulse-key"] == "tp_fake"


# ---------------------------------------------------------------------------
# test_resources_passes_type_param_and_normalizes_envelope
# ---------------------------------------------------------------------------


@respx.mock
async def test_resources_passes_type_param_and_normalizes_envelope():
    """resources(type='project') must forward the type param and normalise the envelope."""
    route = respx.get(f"{BASE_URL}/api/lens/resources").mock(
        return_value=httpx.Response(
            200,
            json={"resources": [{"id": "projects/alpha"}], "count": 1},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.resources(type="project")

    assert route.called
    req = route.calls[0].request
    assert req.url.params["type"] == "project"
    assert result == {"count": 1, "resources": [{"id": "projects/alpha"}]}


# ---------------------------------------------------------------------------
# test_resources_bare_call_sends_no_params
# ---------------------------------------------------------------------------


@respx.mock
async def test_resources_bare_call_sends_no_params():
    """resources() with no arguments must NOT include type or collection query params."""
    route = respx.get(f"{BASE_URL}/api/lens/resources").mock(
        return_value=httpx.Response(200, json={"resources": [], "count": 0})
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.resources()

    assert route.called
    req = route.calls[0].request
    assert "type" not in req.url.params
    assert "collection" not in req.url.params
    assert result == {"count": 0, "resources": []}


# ---------------------------------------------------------------------------
# test_resources_normalizes_null_body
# ---------------------------------------------------------------------------


@respx.mock
async def test_resources_normalizes_null_body():
    """resources() must handle a JSON-null body (resp.json() -> None) and return the empty envelope."""
    # httpx.Response(200, json=None) creates an *empty* body, not "null".
    # We use content=b"null" to produce an actual JSON-null response so resp.json() returns None.
    respx.get(f"{BASE_URL}/api/lens/resources").mock(
        return_value=httpx.Response(
            200,
            content=b"null",
            headers={"content-type": "application/json"},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.resources()

    assert result == {"count": 0, "resources": []}


# ---------------------------------------------------------------------------
# test_get_fetches_resource_by_id
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_fetches_resource_by_id():
    """get('projects/team-pulse') must hit GET /api/lens/resources/projects/team-pulse."""
    route = respx.get(f"{BASE_URL}/api/lens/resources/projects/team-pulse").mock(
        return_value=httpx.Response(200, json={"id": "projects/team-pulse", "title": "Team Pulse"})
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.get("projects/team-pulse")

    assert route.called
    assert result == {"id": "projects/team-pulse", "title": "Team Pulse"}


# ---------------------------------------------------------------------------
# test_get_requires_resource_id
# ---------------------------------------------------------------------------


async def test_get_requires_resource_id():
    """get('') must raise ValueError mentioning 'resource_id'."""
    client = TeamPulseClient(base_url=BASE_URL, auth=FakeAuth())
    with pytest.raises(ValueError, match="resource_id"):
        await client.get("")


@respx.mock
async def test_get_preserves_content_window_without_following():
    full_text = "# Café\n" + "😀界" * 5000
    revision = "lens-text-v1:" + hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    content = "# Café\n"
    body = {
        "id": "corpus/wiki/page.md",
        "content": content,
        "content_revision": revision,
        "metadata": {
            "offset": 0,
            "returned_bytes": len(content.encode("utf-8")),
            "total_bytes": len(full_text.encode("utf-8")),
            "next_offset": len(content.encode("utf-8")),
            "truncated": True,
        },
        "links": ["corpus/wiki/other.md"],
    }
    route = respx.get(f"{BASE_URL}/api/lens/resources/corpus/wiki/page.md").respond(200, json=body)
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.get("corpus/wiki/page.md")
    assert result == body
    assert route.call_count == 1
    assert dict(route.calls[0].request.url.params) == {"offset": "0"}


@respx.mock
async def test_get_forwards_exact_continuation_arguments():
    revision = "lens-text-v1:" + "a" * 64
    route = respx.get(f"{BASE_URL}/api/lens/resources/corpus/wiki/page.md").respond(
        200, json={"content": "尾", "content_revision": revision, "metadata": {"next_offset": None}}
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.get(
            "corpus/wiki/page.md", offset=32766, limit=153600, expected_revision=revision
        )
    assert route.call_count == 1
    assert dict(route.calls[0].request.url.params) == {
        "offset": "32766", "limit": "153600", "expected_revision": revision
    }
    assert result["content_revision"] == revision


@pytest.mark.parametrize(
    ("status", "code", "kwargs"),
    [
        (409, "source_changed", {"offset": 8, "expected_revision": "lens-text-v1:" + "b" * 64}),
        (422, "revision_required", {"offset": 8}),
        (422, "invalid_offset", {"offset": -1}),
        (422, "invalid_limit", {"limit": 0}),
    ],
)
@respx.mock
async def test_get_errors_are_not_retried_or_unpinned(status, code, kwargs):
    error = {"error": {"code": code, "message": "test failure", "status": status}}
    route = respx.get(f"{BASE_URL}/api/lens/resources/corpus/wiki/page.md").respond(status, json=error)
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        with pytest.raises(TeamPulseAPIError) as caught:
            await client.get("corpus/wiki/page.md", **kwargs)
    assert caught.value.status == status
    assert json.loads(caught.value.body) == error
    assert route.call_count == 1


@pytest.mark.parametrize("method", ["resources", "prefix", "search"])
@respx.mock
async def test_list_methods_preserve_all_server_metadata(method):
    paths = {
        "resources": "/api/lens/resources",
        "prefix": "/api/lens/resources/prefix/corpus/wiki",
        "search": "/api/lens/resources/search",
    }
    body = {
        "count": 1,
        "resources": [{
            "id": "corpus/wiki/page.md", "snippet": "a passage",
            "content_revision": "lens-text-v1:" + "c" * 64,
        }],
        "total": 15, "offset": 2, "limit": 1, "future_metadata": {"kept": True},
    }
    route = respx.get(f"{BASE_URL}{paths[method]}").respond(200, json=body)
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        if method == "resources":
            result = await client.resources(collection="corpus", limit=1, offset=2)
        elif method == "prefix":
            result = await client.prefix("corpus/wiki", limit=1, offset=2)
        else:
            result = await client.search("passage", limit=1, collection="corpus")
    assert result == body
    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["limit"] == "1"
    if method != "search":
        assert params["offset"] == "2"
    else:
        assert "offset" not in params


@pytest.mark.parametrize("method", ["resources", "prefix"])
@respx.mock
async def test_listing_defaults_remain_unbounded_and_explicit_zero_is_forwarded(method):
    path = "/api/lens/resources" + ("/prefix/corpus" if method == "prefix" else "")
    route = respx.get(f"{BASE_URL}{path}").respond(200, json={"count": 0, "resources": []})
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        call = getattr(client, method)
        args = ("corpus",) if method == "prefix" else ()
        await call(*args)
        await call(*args, offset=0)
    assert dict(route.calls[0].request.url.params) == {}
    assert dict(route.calls[1].request.url.params) == {"offset": "0"}


@respx.mock
async def test_search_unavailable_is_not_a_successful_zero_hit_result():
    error = {"error": {"code": "search_unavailable", "message": "Index unavailable", "status": 503}}
    route = respx.get(f"{BASE_URL}/api/lens/resources/search").respond(503, json=error)
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        with pytest.raises(TeamPulseAPIError) as caught:
            await client.search("topic", collection="corpus")
    assert caught.value.status == 503
    assert json.loads(caught.value.body) == error
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# test_whoami_hits_correct_path
# ---------------------------------------------------------------------------


@respx.mock
async def test_whoami_hits_correct_path():
    """whoami() hits /api/lens/me."""
    whoami_route = respx.get(f"{BASE_URL}/api/lens/me").mock(return_value=httpx.Response(200, json={"handle": "jdoe"}))
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        whoami_result = await client.whoami()

    assert whoami_route.called
    assert whoami_result == {"handle": "jdoe"}


# ---------------------------------------------------------------------------
# Task 7: search, prefix, ask
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_sends_q_and_limit_and_normalizes():
    """search(q='widgets') must forward q and default limit=50, then normalize envelope."""
    route = respx.get(f"{BASE_URL}/api/lens/resources/search").mock(
        return_value=httpx.Response(
            200,
            json={"resources": [{"id": "projects/widgets"}], "count": 1},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.search(q="widgets")

    assert route.called
    req = route.calls[0].request
    assert req.url.params["q"] == "widgets"
    assert req.url.params["limit"] == "50"
    assert result == {"count": 1, "resources": [{"id": "projects/widgets"}]}


@respx.mock
async def test_search_honors_explicit_limit_and_collection():
    """search(q=..., limit=10, collection='docs') must forward limit and collection params."""
    route = respx.get(f"{BASE_URL}/api/lens/resources/search").mock(
        return_value=httpx.Response(200, json={"resources": [], "count": 0})
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.search(q="docs-query", limit=10, collection="docs")

    assert route.called
    req = route.calls[0].request
    assert req.url.params["limit"] == "10"
    assert req.url.params["collection"] == "docs"
    assert result == {"count": 0, "resources": []}


async def test_search_requires_q():
    """search('') must raise ValueError mentioning 'q is required'."""
    client = TeamPulseClient(base_url=BASE_URL, auth=FakeAuth())
    with pytest.raises(ValueError, match="q is required"):
        await client.search(q="")


@respx.mock
async def test_prefix_hits_path_and_normalizes():
    """prefix('projects') must GET /api/lens/resources/prefix/projects and normalize."""
    route = respx.get(f"{BASE_URL}/api/lens/resources/prefix/projects").mock(
        return_value=httpx.Response(
            200,
            json={"resources": [{"id": "projects/team-pulse"}], "count": 1},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.prefix("projects")

    assert route.called
    assert result == {"count": 1, "resources": [{"id": "projects/team-pulse"}]}


async def test_prefix_requires_prefix():
    """prefix('') must raise ValueError mentioning 'prefix is required'."""
    client = TeamPulseClient(base_url=BASE_URL, auth=FakeAuth())
    with pytest.raises(ValueError, match="prefix is required"):
        await client.prefix("")


@respx.mock
async def test_ask_posts_prompt_and_omits_focus_when_none():
    """ask(prompt=...) must POST body={'prompt': ...} and NOT include 'focus' when focus=None."""
    route = respx.post(f"{BASE_URL}/api/lens/ask").mock(
        return_value=httpx.Response(
            200,
            json={"content": "All good.", "prompt_used": "how is the team?", "provenance": {}},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.ask(prompt="how is the team?")

    assert route.called
    import json

    body = json.loads(route.calls[0].request.content)
    assert body == {"prompt": "how is the team?"}
    assert "focus" not in body
    assert result["content"] == "All good."


@respx.mock
async def test_ask_includes_focus_when_given():
    """ask(prompt=..., focus='projects/team-pulse') must include focus in the POST body."""
    route = respx.post(f"{BASE_URL}/api/lens/ask").mock(
        return_value=httpx.Response(
            200,
            json={"content": "On track.", "prompt_used": "status?", "provenance": {}},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.ask(prompt="status?", focus="projects/team-pulse")

    assert route.called
    import json

    body = json.loads(route.calls[0].request.content)
    assert body["focus"] == "projects/team-pulse"
    assert result["content"] == "On track."
