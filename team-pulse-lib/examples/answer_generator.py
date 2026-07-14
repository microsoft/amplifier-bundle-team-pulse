# SPDX-License-Identifier: MIT
"""Example: answer-generator loop — the realistic headless partner flow.

Fetches all active questions from Team Pulse, synthesises a short answer for
each one, and submits them as bare Phase-0 answers (no ``user_id``, no
``metadata``).  This mirrors the session-mining loop an Amplifier agent would
run to populate Team Pulse with AI-synthesised reflections.

Usage (self-contained — auto-starts the fake server when no real URL is set)::

    uv run python examples/answer_generator.py

Usage against a real server::

    AMPLIFIER_TEAM_PULSE_URL=https://your-server \\
    AMPLIFIER_TEAM_PULSE_KEY=tp_your_key \\
        uv run python examples/answer_generator.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from team_pulse_lib import TeamPulseClient
from team_pulse_lib.models import AnswerUpload, Question, SubmittedAnswer

# ---------------------------------------------------------------------------
# Answer synthesiser
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _synthesise_answer(question: Question) -> str:
    """Generate a short placeholder answer for the given question.

    In production this would be replaced by an LLM call (e.g. via Amplifier)
    that mines session context to produce a genuine reflection.  The lookback
    window from :attr:`~team_pulse_lib.models.Question.lookback_days` is
    referenced in the answer so the synthesiser could scope its analysis.
    """
    lb_clause = f" (looking back {question.lookback_days} days)" if question.lookback_days else ""
    return (
        f"[AI-synthesised{lb_clause}] The team focused on the auth-service refactor, "
        "closed three critical-path pull requests, and ran a retrospective that surfaced "
        "two process improvements now tracked in the team backlog. No blocking incidents."
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def main(
    base_url: str | None = None,
    api_key: str = "tp_demo_key_examples",
    user_id: str = "",
) -> dict:
    """Fetch active questions, synthesise answers, submit them bare (Phase-0 safe).

    Args:
        base_url: Server URL.  Takes precedence over the ``AMPLIFIER_TEAM_PULSE_URL``
            env var.  If neither is set the client constructor will raise.
        api_key: API key starting with ``tp_``.  Overridden by the
            ``AMPLIFIER_TEAM_PULSE_KEY`` env var when set.
        user_id: User to attribute answers to.  Empty string (default) keeps
            submits bare / Phase-0 safe — no guardrail is triggered.

    Returns:
        ``dict`` with ``questions`` (``list[Question]``) and ``submitted``
        (``list[SubmittedAnswer]``).  Intended for test assertions; the function
        also prints a human-readable summary as a side effect.
    """
    url: str = base_url or os.environ.get("AMPLIFIER_TEAM_PULSE_URL") or ""
    key: str = os.environ.get("AMPLIFIER_TEAM_PULSE_KEY") or api_key

    print("\n=== Team Pulse: Answer Generator ===")
    print(f"Server: {url}")

    questions: list[Question] = []
    submitted: list[SubmittedAnswer] = []

    # Recommended construction: connect() infers api-key auth from the tp_ key.
    async with TeamPulseClient.connect(base_url=url, key=key) as client:
        # Phase 1: discover active questions
        questions = await client.fetch_questions(status="active")
        print(f"\n[Discovered {len(questions)} active question(s)]")
        for q in questions:
            lb = f"{q.lookback_days}d" if q.lookback_days is not None else "no lookback"
            print(f"  [{q.question_id}]  ({lb})")
            print(f"    {q.question}")

        # Phase 2: synthesise + submit
        print("\n[Submitting answers]")
        generated_at = _now_iso()
        for q in questions:
            answer_text = _synthesise_answer(q)
            payload = AnswerUpload(
                question_id=q.question_id,
                user_id=user_id,  # empty by default → bare submit
                answer=answer_text,
                generated_at=generated_at,
                metadata={"source_session_ids": ["example-session-generator-001"]},
            )
            result: SubmittedAnswer = await client.upload_answer(payload)
            submitted.append(result)
            icon = "✓" if result.created else "↺"
            print(f"  {icon}  [{result.question_id}]  id={result.id!r}  created={result.created}")

    print(f"\n[Summary]  Pushed {len(submitted)}/{len(questions)} answer(s)")
    for s in submitted:
        print(f"  answer_id={s.id!r}  question_id={s.question_id!r}  created={s.created}")
    print()

    return {"questions": questions, "submitted": submitted}


if __name__ == "__main__":
    _env_url = os.environ.get("AMPLIFIER_TEAM_PULSE_URL")
    if _env_url:
        asyncio.run(main(base_url=_env_url))
    else:
        # No real server configured — spin up the stdlib-only fake server.
        from fake_team_pulse_server import FakeTeamPulseServer

        with FakeTeamPulseServer(advertise_metadata=False) as _fake_url:
            asyncio.run(main(base_url=_fake_url))
