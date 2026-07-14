# SPDX-License-Identifier: MIT
"""Tests for team_pulse_lib.models — public API shapes."""

from __future__ import annotations

import dataclasses

from team_pulse_lib.models import AnswerUpload, ClientInfo, Question, SubmittedAnswer


class TestQuestion:
    def test_lookback_days_defaults_to_none(self) -> None:
        q = Question(question_id="q1", question="What did you do?")
        assert q.lookback_days is None

    def test_accepts_lookback_days(self) -> None:
        q = Question(question_id="q1", question="What did you do?", lookback_days=30)
        assert q.lookback_days == 30


class TestAnswerUpload:
    def test_metadata_defaults_to_empty_dict(self) -> None:
        a = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="I did stuff.",
            generated_at="2026-06-25T17:00:00Z",
        )
        assert a.metadata == {}

    def test_source_session_ids_field_is_gone(self) -> None:
        field_names = {f.name for f in dataclasses.fields(AnswerUpload)}
        assert "source_session_ids" not in field_names

    def test_construct_without_sessions_uses_metadata(self) -> None:
        a = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="text",
            generated_at="2026-06-25T17:00:00Z",
            metadata={"source_session_ids": ["s1"]},
        )
        assert a.metadata == {"source_session_ids": ["s1"]}

    def test_metadata_not_shared_between_instances(self) -> None:
        a1 = AnswerUpload(
            question_id="q1",
            user_id="u1",
            answer="Answer 1",
            generated_at="2026-06-25T17:00:00Z",
        )
        a2 = AnswerUpload(
            question_id="q2",
            user_id="u2",
            answer="Answer 2",
            generated_at="2026-06-25T18:00:00Z",
        )
        a1.metadata["key"] = "value"
        assert "key" not in a2.metadata, "metadata must not be shared between instances"


class TestSubmittedAnswer:
    def test_field_tuple(self) -> None:
        field_names = {f.name for f in dataclasses.fields(SubmittedAnswer)}
        assert field_names == {"id", "question_id", "created"}

    def test_created_false_on_idempotent(self) -> None:
        sa = SubmittedAnswer(id="ans-123", question_id="q1", created=False)
        assert sa.created is False


class TestClientInfo:
    def test_full_shape(self) -> None:
        ci = ClientInfo(
            base_url="https://example.com",
            auth_mode="key",
            api_app_id=None,
            credential_type="api_key",
            forced=False,
            resolved=False,
        )
        assert ci.base_url == "https://example.com"
        assert ci.auth_mode == "key"
        assert ci.api_app_id is None
        assert ci.credential_type == "api_key"
        assert ci.forced is False
        assert ci.resolved is False

    def test_server_supports_metadata_field_is_gone(self) -> None:
        field_names = {f.name for f in dataclasses.fields(ClientInfo)}
        assert "server_supports_metadata" not in field_names
