# SPDX-License-Identifier: MIT
"""Tests for fetch_questions and fetch_question typed API methods (Task 8).

Covers:
- fetch_questions: defaults to active-only, filters archived, status='all', lookback_days edge cases
- fetch_question: single fetch by ID returns a Question dataclass
- upload_answer: bare submit path, 201 vs 200, no capability probe (Task 9)
"""

from __future__ import annotations

import json

import httpx
import respx

from team_pulse_lib.client import TeamPulseClient
from team_pulse_lib.models import AnswerUpload, Question

# ---------------------------------------------------------------------------
# Shared test double
# ---------------------------------------------------------------------------

BASE_URL = "https://team-pulse.test"


class FakeAuth:
    """Minimal AuthStrategy stub — always succeeds and injects X-Team-Pulse-Key."""

    async def headers(self) -> dict[str, str]:
        return {"X-Team-Pulse-Key": "tp_fake"}


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_MIXED_QUESTIONS = {
    "resources": [
        {
            "id": "questions/active-a",
            "type": "question",
            "data": {
                "id": "active-a",
                "question": "A?",
                "status": "active",
                "lookback_days": 30,
            },
        },
        {
            "id": "questions/archived-b",
            "type": "question",
            "data": {
                "id": "archived-b",
                "question": "B?",
                "status": "archived",
            },
        },
        {
            "id": "questions/active-c",
            "type": "question",
            "data": {
                "id": "active-c",
                "question": "C?",
                "status": "active",
            },
        },
    ]
}


# ---------------------------------------------------------------------------
# test_fetch_questions_defaults_to_active_only
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_questions_defaults_to_active_only():
    """fetch_questions() defaults to status='active', returns only active questions; request carries type=question."""
    route = respx.get(f"{BASE_URL}/api/lens/resources").mock(return_value=httpx.Response(200, json=_MIXED_QUESTIONS))
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.fetch_questions()

    assert route.called
    req = route.calls[0].request
    assert req.url.params["type"] == "question"
    # status is now sent to the server (which filters authoritatively); the
    # client-side filter remains as a defensive fallback for older servers.
    assert req.url.params["status"] == "active"
    assert len(result) == 2
    ids = {q.question_id for q in result}
    assert ids == {"active-a", "active-c"}


@respx.mock
async def test_fetch_questions_sends_status_param_to_server():
    """fetch_questions(status=...) forwards the status query param to the server."""
    route = respx.get(f"{BASE_URL}/api/lens/resources").mock(
        return_value=httpx.Response(200, json=_MIXED_QUESTIONS)
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        await client.fetch_questions(status="all")
    assert route.calls[0].request.url.params["status"] == "all"


@respx.mock
async def test_resources_forwards_status_param():
    """resources(status=...) forwards status so the generic tool can filter questions."""
    route = respx.get(f"{BASE_URL}/api/lens/resources").mock(
        return_value=httpx.Response(200, json=_MIXED_QUESTIONS)
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        await client.resources(type="question", status="archived")
    req = route.calls[0].request
    assert req.url.params["type"] == "question"
    assert req.url.params["status"] == "archived"


# ---------------------------------------------------------------------------
# test_fetch_questions_archived_filters_to_archived
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_questions_archived_filters_to_archived():
    """fetch_questions(status='archived') returns only archived questions."""
    respx.get(f"{BASE_URL}/api/lens/resources").mock(return_value=httpx.Response(200, json=_MIXED_QUESTIONS))
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.fetch_questions(status="archived")

    assert len(result) == 1
    assert result[0].question_id == "archived-b"


# ---------------------------------------------------------------------------
# test_fetch_questions_all_returns_everything
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_questions_all_returns_everything():
    """fetch_questions(status='all') returns all 3 questions regardless of status."""
    respx.get(f"{BASE_URL}/api/lens/resources").mock(return_value=httpx.Response(200, json=_MIXED_QUESTIONS))
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.fetch_questions(status="all")

    assert len(result) == 3


# ---------------------------------------------------------------------------
# test_fetch_questions_missing_lookback_days_is_none
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_questions_missing_lookback_days_is_none():
    """Questions missing lookback_days have lookback_days=None; present values are preserved."""
    respx.get(f"{BASE_URL}/api/lens/resources").mock(return_value=httpx.Response(200, json=_MIXED_QUESTIONS))
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.fetch_questions(status="all")

    by_id = {q.question_id: q for q in result}
    assert by_id["active-a"].lookback_days == 30
    assert by_id["active-c"].lookback_days is None


# ---------------------------------------------------------------------------
# test_fetch_question_returns_single_question
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_question_returns_single_question():
    """fetch_question('active-a') hits GET /api/lens/resources/questions/active-a and returns a Question."""
    route = respx.get(f"{BASE_URL}/api/lens/resources/questions/active-a").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "questions/active-a",
                "type": "question",
                "data": {
                    "id": "active-a",
                    "question": "A?",
                    "status": "active",
                    "lookback_days": 14,
                },
            },
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.fetch_question("active-a")

    assert route.called
    assert isinstance(result, Question)
    assert result.question == "A?"
    assert result.lookback_days == 14


# ---------------------------------------------------------------------------
# answer_factory — bare submit: empty user_id + empty metadata
# ---------------------------------------------------------------------------


def answer_factory(**kwargs: object) -> AnswerUpload:
    """Return an AnswerUpload with bare-submit defaults (empty user_id, empty metadata)."""
    defaults: dict[str, object] = {
        "question_id": "effective-practices",
        "user_id": "",
        "answer": "AI synthesised answer text",
        "generated_at": "2026-06-25T17:00:00Z",
    }
    defaults.update(kwargs)
    return AnswerUpload(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# test_upload_answer_sends_exact_partner_wire_body_on_201
# ---------------------------------------------------------------------------


@respx.mock
async def test_upload_answer_sends_exact_partner_wire_body_on_201():
    """upload_answer sends EXACTLY {question_id, user_id, generated_at, answer, metadata}; metadata always present; no source/respondent/source_session_ids."""
    route = respx.post(f"{BASE_URL}/api/lens/answers").mock(
        return_value=httpx.Response(
            201,
            json={"answer": {"id": "ans-1", "question_id": "effective-practices"}},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.upload_answer(answer_factory(user_id="alice"))

    assert route.called
    body = json.loads(route.calls[0].request.content)
    # Exactly the five partner-canonical keys — nothing more, nothing less.
    assert set(body.keys()) == {"question_id", "user_id", "generated_at", "answer", "metadata"}
    assert body["question_id"] == "effective-practices"
    assert body["user_id"] == "alice"
    assert body["metadata"] == {}  # always present, even when empty
    # Legacy fields must be gone.
    assert "source" not in body
    assert "source_session_ids" not in body
    assert "respondent_provider" not in body
    assert "respondent_id" not in body
    # Response mapping: id is nested under "answer" in real server response.
    assert result.created is True
    assert result.id == "ans-1"
    assert result.question_id == "effective-practices"


# ---------------------------------------------------------------------------
# test_upload_answer_created_false_on_idempotent_200
# ---------------------------------------------------------------------------


@respx.mock
async def test_upload_answer_created_false_on_idempotent_200():
    """upload_answer returns created=False on 200 (idempotent re-submit)."""
    respx.post(f"{BASE_URL}/api/lens/answers").mock(
        return_value=httpx.Response(
            200,
            json={"answer": {"id": "ans-1", "question_id": "effective-practices"}},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        result = await client.upload_answer(answer_factory())

    assert result.created is False


# ---------------------------------------------------------------------------
# test_upload_answer_does_not_probe_capability_for_bare_submit
# ---------------------------------------------------------------------------


@respx.mock
async def test_upload_answer_does_not_probe_capability_for_bare_submit():
    """upload_answer bare submit must NOT call GET /api/lens/info (no capability probe)."""
    info_route = respx.get(f"{BASE_URL}/api/lens/info").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{BASE_URL}/api/lens/answers").mock(
        return_value=httpx.Response(
            201,
            json={"answer": {"id": "ans-1", "question_id": "effective-practices"}},
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        await client.upload_answer(answer_factory())

    assert info_route.called is False
