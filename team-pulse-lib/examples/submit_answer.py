# SPDX-License-Identifier: MIT
"""Example: submitting answers to Team Pulse (schema v1).

Two scenarios, both succeeding against the same server:

1. **BARE SUBMIT** — no ``user_id``, empty ``metadata``.
2. **METADATA SUBMIT** — a ``user_id`` plus a ``metadata`` bag that carries
   session provenance (``source_session_ids``) and any other opaque fields.

There is no capability guardrail: the schema-v1 server persists ``metadata``
verbatim, and the bundle deploys server-first so a metadata-sending client is
never ahead of the server.

Usage (self-contained — auto-starts the stdlib fake server)::

    uv run python examples/submit_answer.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from team_pulse_lib import TeamPulseClient
from team_pulse_lib.models import AnswerUpload, SubmittedAnswer


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def main(*, base_url: str, api_key: str = "tp_demo") -> dict:
    """Run a bare submit and a metadata submit; return results for assertions.

    Args:
        base_url: Team Pulse server URL.
        api_key: API key starting with ``tp_``.  Overridden by the
            ``AMPLIFIER_TEAM_PULSE_KEY`` env var when set.

    Returns:
        ``dict`` with ``bare`` and ``meta_submit`` (both
        :class:`~team_pulse_lib.models.SubmittedAnswer`).
    """
    key: str = os.environ.get("AMPLIFIER_TEAM_PULSE_KEY") or api_key

    # -----------------------------------------------------------------------
    # Scenario 1: BARE SUBMIT — empty user_id, empty metadata
    # -----------------------------------------------------------------------
    print("\n=== Scenario 1: Bare Submit ===")
    bare_payload = AnswerUpload(
        question_id="higher-level-work",
        user_id="",
        answer=(
            "Shipped the auth refactor, reviewed three pull requests, "
            "and unblocked two teammates stuck on the migration script."
        ),
        generated_at=_now_iso(),
    )
    print(f"  question_id : {bare_payload.question_id}")
    print(f"  metadata    : {bare_payload.metadata}  (empty)")

    bare_result: SubmittedAnswer
    async with TeamPulseClient.connect(base_url=base_url, key=key) as client:
        bare_result = await client.upload_answer(bare_payload)
    print(
        f"  -> SubmittedAnswer(id={bare_result.id!r}, "
        f"question_id={bare_result.question_id!r}, created={bare_result.created})"
    )

    # -----------------------------------------------------------------------
    # Scenario 2: METADATA SUBMIT — user_id + metadata (sessions live inside)
    # -----------------------------------------------------------------------
    print("\n=== Scenario 2: Metadata Submit ===")
    meta_payload = AnswerUpload(
        question_id="effective-practices",
        user_id="alice",
        answer="Answer with full metadata and user attribution.",
        generated_at=_now_iso(),
        metadata={
            "source_session_ids": ["session-xyz789"],
            "model": "claude-opus-4-6",
            "confidence": 0.92,
        },
    )
    print(f"  question_id : {meta_payload.question_id}")
    print(f"  user_id     : {meta_payload.user_id!r}")
    print(f"  metadata    : {meta_payload.metadata}")

    meta_result: SubmittedAnswer
    async with TeamPulseClient.connect(base_url=base_url, key=key) as client:
        meta_result = await client.upload_answer(meta_payload)
    print(
        f"  -> SubmittedAnswer(id={meta_result.id!r}, "
        f"question_id={meta_result.question_id!r}, created={meta_result.created})"
    )

    print("\n=== Summary ===")
    print("  1. Bare submit     -> created=True")
    print("  2. Metadata submit -> created (sessions carried inside metadata)")
    print()

    return {"bare": bare_result, "meta_submit": meta_result}


if __name__ == "__main__":
    from fake_team_pulse_server import FakeTeamPulseServer

    with FakeTeamPulseServer() as _url:
        asyncio.run(main(base_url=_url))
