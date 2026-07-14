# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Shim tests for TeamPulseSubmitAnswerTool — verifies it maps tool input →
AnswerUpload → client.upload_answer and surfaces errors correctly.

These tests focus on the shim contract (not the HTTP layer):
- _call builds AnswerUpload with correct fields; sessions live in metadata
- client.upload_answer is awaited exactly once
- SubmittedAnswer is converted to a JSON-able dict via _as_jsonable
- TeamPulseAPIError envelope passes through (code preserved)
- Input schema is correct (required fields, pattern, no 'source_session_ids', optional metadata)

NOTE: We use spec=_LibClient on the mock so that the _LensTool.execute()
method does not mistake the mock for a _ClientProvider (AsyncMock
auto-creates all attributes including .client, which would fool the
``callable(getattr(self._client, "client", None))`` check).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from team_pulse_lib import (
    AnswerUpload,
    SubmittedAnswer,
)
from team_pulse_lib import (
    TeamPulseClient as _LibClient,
)

from amplifier_module_tool_team_pulse import TeamPulseSubmitAnswerTool


class _APIError(Exception):
    """Stub for old-style TeamPulseAPIError with .envelope — duck-typed by _error_result."""

    def __init__(self, envelope: dict) -> None:
        self.envelope = envelope
        super().__init__(str(envelope))


# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

_QUESTION_ID = "higher-level-work"
_USER_ID = "jdoe"
_ANSWER = "Based on recent session analysis, this person focuses heavily on ..."
_SESSION_IDS = [
    "846491a9-8082-4e0c-95f9-32b90a3d15a0",
    "fe291191-419d-4a97-b42b-d76e6193c5e7",
]
_GENERATED_AT = "2026-05-31T02:15:30.000+00:00"

_VALID_INPUT: dict = {
    "question_id": _QUESTION_ID,
    "user_id": _USER_ID,
    "answer": _ANSWER,
    "metadata": {"source_session_ids": _SESSION_IDS},
    "generated_at": _GENERATED_AT,
}

_DEFAULT_SA = SubmittedAnswer(id="a1", question_id=_QUESTION_ID, created=False)


def _make_mock_client(
    *,
    return_value: object | None = None,
    side_effect: BaseException | None = None,
) -> AsyncMock:
    """Return an AsyncMock(spec=_LibClient) with upload_answer configured.

    Using spec=_LibClient is critical: it prevents AsyncMock from
    auto-creating a callable .client attribute, which would cause execute()
    to treat the mock as a _ClientProvider and resolve a nested mock instead
    of the direct client.
    """
    mock_client = AsyncMock(spec=_LibClient)
    if side_effect is not None:
        mock_client.upload_answer.side_effect = side_effect
    else:
        mock_client.upload_answer.return_value = return_value if return_value is not None else _DEFAULT_SA
    return mock_client


# ---------------------------------------------------------------------------
# Scenario 1: builds AnswerUpload and calls upload_answer
# ---------------------------------------------------------------------------


async def test_upload_answer_awaited_once():
    """_call must await upload_answer exactly once."""
    mock_client = _make_mock_client()
    tool = TeamPulseSubmitAnswerTool(mock_client)
    await tool.execute(_VALID_INPUT)
    mock_client.upload_answer.assert_awaited_once()


async def test_answer_upload_carries_all_input_fields():
    """AnswerUpload passed to upload_answer must carry all input fields; sessions live in metadata."""
    mock_client = _make_mock_client()
    tool = TeamPulseSubmitAnswerTool(mock_client)
    await tool.execute(_VALID_INPUT)

    arg: AnswerUpload = mock_client.upload_answer.call_args[0][0]
    assert isinstance(arg, AnswerUpload)
    assert arg.question_id == _QUESTION_ID
    assert arg.user_id == _USER_ID
    assert arg.answer == _ANSWER
    assert arg.generated_at == _GENERATED_AT
    assert arg.metadata == {"source_session_ids": _SESSION_IDS}


async def test_answer_upload_metadata_defaults_to_empty_dict():
    """When no metadata is supplied, AnswerUpload.metadata is {}."""
    mock_client = _make_mock_client()
    tool = TeamPulseSubmitAnswerTool(mock_client)
    bare_input = {k: v for k, v in _VALID_INPUT.items() if k != "metadata"}
    await tool.execute(bare_input)

    arg: AnswerUpload = mock_client.upload_answer.call_args[0][0]
    assert arg.metadata == {}


# ---------------------------------------------------------------------------
# Scenario 2: output is JSON-able SubmittedAnswer
# ---------------------------------------------------------------------------


async def test_output_is_dict_with_id_question_id_created():
    """SubmittedAnswer return value must be converted to a plain dict."""
    sa = SubmittedAnswer(id="a1", question_id=_QUESTION_ID, created=False)
    mock_client = _make_mock_client(return_value=sa)
    tool = TeamPulseSubmitAnswerTool(mock_client)

    result = await tool.execute(_VALID_INPUT)

    assert result.success is True
    output = result.output
    assert output["id"] == "a1"
    assert output["question_id"] == _QUESTION_ID
    assert output["created"] is False


async def test_output_is_json_serializable():
    """The output dict must survive json.dumps without error."""
    sa = SubmittedAnswer(id="a1", question_id=_QUESTION_ID, created=False)
    mock_client = _make_mock_client(return_value=sa)
    tool = TeamPulseSubmitAnswerTool(mock_client)

    result = await tool.execute(_VALID_INPUT)

    assert result.success is True
    # Must not raise
    serialised = json.dumps(result.output)
    assert "a1" in serialised


# ---------------------------------------------------------------------------
# Scenario 3: API error passthrough (code preserved)
# ---------------------------------------------------------------------------


async def test_api_error_envelope_passes_through():
    """TeamPulseAPIError with envelope code='unknown_question' must be preserved."""
    error_env = {"code": "unknown_question", "message": "question 'nope' not found", "status": 400}
    mock_client = _make_mock_client(side_effect=_APIError(error_env))
    tool = TeamPulseSubmitAnswerTool(mock_client)

    result = await tool.execute(_VALID_INPUT)

    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "unknown_question"


# ---------------------------------------------------------------------------
# Scenario 5: Input schema
# ---------------------------------------------------------------------------


def _schema() -> dict:
    return TeamPulseSubmitAnswerTool(AsyncMock(spec=_LibClient)).input_schema


def test_schema_required_fields_match():
    """Required fields must be exactly the 4 caller-supplied fields (no source_session_ids)."""
    assert set(_schema()["required"]) == {
        "question_id",
        "user_id",
        "answer",
        "generated_at",
    }


def test_schema_has_no_source_session_ids():
    """source_session_ids is gone — sessions now live inside metadata."""
    assert "source_session_ids" not in _schema()["properties"]


def test_schema_allows_optional_metadata():
    """metadata is an optional object property (sessions live inside it)."""
    props = _schema()["properties"]
    assert "metadata" in props
    assert props["metadata"]["type"] == "object"
    assert "metadata" not in _schema()["required"]


def test_schema_additional_properties_false():
    """additionalProperties must be False to reject unknown keys."""
    assert _schema().get("additionalProperties") is False


def test_schema_question_id_has_bare_slug_pattern():
    """question_id must carry the bare-slug regex to reject hierarchical IDs."""
    props = _schema()["properties"]
    assert "pattern" in props["question_id"]
    assert props["question_id"]["pattern"] == "^[a-z0-9][a-z0-9-]*$"


def test_schema_has_no_source_field():
    """'source' is hardcoded by the lib — must NOT appear as a caller-supplied param."""
    assert "source" not in _schema()["properties"]
