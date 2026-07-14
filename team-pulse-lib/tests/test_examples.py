# SPDX-License-Identifier: MIT
# ruff: noqa: E402  -- examples/ path must be added before importing example modules
"""Integration tests for the examples/ scripts.

Tests make real HTTP calls against FakeTeamPulseServer running on a genuine
127.0.0.1 socket — no respx mocking, no monkey-patching.  Each test gets a
fresh server instance so submitted_answers do not bleed across tests.

Mirrors the existing test style (asyncio_mode="auto", no @pytest.mark.asyncio).
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make examples/ importable before the example-module imports below.
# ---------------------------------------------------------------------------
_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
if str(_EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_DIR))

import answer_generator as ag_ex
import fetch_questions as fq_ex
import submit_answer as sa_ex
from fake_team_pulse_server import FakeTeamPulseServer

from team_pulse_lib import DEFAULT_API_APP_ID
from team_pulse_lib.models import Question, SubmittedAnswer

# ---------------------------------------------------------------------------
# Fixture constants — must match FakeTeamPulseServer's _QUESTIONS list exactly
# ---------------------------------------------------------------------------

# Active questions in the fake fixture data:
#   higher-level-work, effective-practices, team-blockers
_ACTIVE_IDS: frozenset[str] = frozenset({"higher-level-work", "effective-practices", "team-blockers"})
_ACTIVE_COUNT: int = len(_ACTIVE_IDS)
_TOTAL_COUNT: int = _ACTIVE_COUNT + 1  # + old-retro (archived)

_API_KEY: str = "tp_test_examples_runner"


# ===========================================================================
# fetch_questions tests
# ===========================================================================


async def test_fetch_questions_returns_active_only() -> None:
    """main() returns only active questions by default."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    active = result["active"]
    assert isinstance(active, list)
    assert len(active) == _ACTIVE_COUNT


async def test_fetch_questions_ids_match_fixture() -> None:
    """Active question IDs exactly match the fake-server fixture data."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    ids = {q.question_id for q in result["active"]}
    assert ids == _ACTIVE_IDS


async def test_fetch_questions_all_returns_active_plus_archived() -> None:
    """fetch_questions(status='all') returns both active and archived questions."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    assert len(result["all"]) == _TOTAL_COUNT


async def test_fetch_questions_all_are_question_instances() -> None:
    """Every item returned is a Question dataclass."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    assert all(isinstance(q, Question) for q in result["active"])
    assert all(isinstance(q, Question) for q in result["all"])


async def test_fetch_questions_lookback_days_present_and_absent() -> None:
    """Questions with lookback_days carry the value; absent ones return None."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    by_id = {q.question_id: q for q in result["active"]}
    assert by_id["higher-level-work"].lookback_days == 7
    assert by_id["effective-practices"].lookback_days == 14
    assert by_id["team-blockers"].lookback_days is None  # absent in fixture data


async def test_fetch_question_single_lookup_returns_correct_question() -> None:
    """fetch_question returns the Question matching the first active question's slug."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    single = result["single"]
    assert single is not None
    assert isinstance(single, Question)
    assert single.question_id == result["active"][0].question_id


async def test_describe_returns_correct_client_info() -> None:
    """describe() snapshot carries the correct provenance fields; no secret exposed."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await fq_ex.main(base_url=url, api_key=_API_KEY)

    info = result["info"]
    assert info.base_url == url
    assert info.auth_mode == "key"
    assert info.credential_type == "api_key"
    assert info.resolved is True
    # connect() always carries the service-owned default audience in ResolvedConfig,
    # even for key auth (the app id is only *used* when az auth is selected).  Raw
    # __init__ construction would leave this None; connect() populates it.
    assert info.api_app_id == DEFAULT_API_APP_ID


# ===========================================================================
# submit_answer tests
# ===========================================================================


async def test_bare_submit_returns_submitted_answer_created_true() -> None:
    """Bare submit (no metadata) returns SubmittedAnswer(created=True)."""
    with FakeTeamPulseServer() as url:
        result = await sa_ex.main(base_url=url, api_key=_API_KEY)

    bare = result["bare"]
    assert isinstance(bare, SubmittedAnswer)
    assert bare.created is True
    assert bare.question_id == "higher-level-work"


async def test_metadata_submit_succeeds_and_carries_sessions_in_metadata() -> None:
    """A submit WITH metadata succeeds; session ids live inside metadata."""
    server = FakeTeamPulseServer()
    url = server.start()
    try:
        result = await sa_ex.main(base_url=url, api_key=_API_KEY)

        meta = result["meta_submit"]
        assert isinstance(meta, SubmittedAnswer)

        # The recorded body for the meta submit carries sessions inside metadata.
        recorded = next(a for a in server.submitted_answers if a.get("metadata"))
        assert "source_session_ids" in recorded["metadata"]
    finally:
        server.stop()


# ===========================================================================
# answer_generator tests
# ===========================================================================


async def test_answer_generator_pushes_one_answer_per_active_question() -> None:
    """answer_generator submits exactly one answer for each active question."""
    server = FakeTeamPulseServer(advertise_metadata=False)
    url = server.start()
    try:
        result = await ag_ex.main(base_url=url, api_key=_API_KEY)

        submitted = result["submitted"]
        questions = result["questions"]

        assert len(submitted) == _ACTIVE_COUNT, f"expected {_ACTIVE_COUNT} answers, got {len(submitted)}"
        assert len(submitted) == len(questions)
        assert all(isinstance(s, SubmittedAnswer) for s in submitted)
        # Fresh server → all are newly created
        assert all(s.created is True for s in submitted)

        # Server recorded exactly the same answers
        recorded_qids = {a["question_id"] for a in server.submitted_answers}
        submitted_qids = {s.question_id for s in submitted}
        assert recorded_qids == submitted_qids
    finally:
        server.stop()


async def test_answer_generator_fetches_only_active_questions() -> None:
    """answer_generator respects the active-only filter — archived question excluded."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await ag_ex.main(base_url=url, api_key=_API_KEY)

    question_ids = {q.question_id for q in result["questions"]}
    assert question_ids == _ACTIVE_IDS
    assert "old-retro" not in question_ids  # must not include the archived fixture


async def test_answer_generator_submitted_question_ids_match_fetched() -> None:
    """Submitted answer question_ids match the fetched active question IDs exactly."""
    with FakeTeamPulseServer(advertise_metadata=False) as url:
        result = await ag_ex.main(base_url=url, api_key=_API_KEY)

    fetched_ids = {q.question_id for q in result["questions"]}
    submitted_ids = {s.question_id for s in result["submitted"]}
    assert submitted_ids == fetched_ids
