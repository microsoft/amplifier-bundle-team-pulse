# SPDX-License-Identifier: MIT
"""Example: reading questions from Team Pulse.

Demonstrates:
  • Building a client with ``TeamPulseClient.connect(base_url=..., key=...)``
    — the recommended factory (a ``tp_`` key infers api-key auth; no Azure needed)
  • ``async with client:`` context manager — credential validated eagerly
  • ``fetch_questions(status="active")`` → ``list[Question]``
  • ``fetch_question(slug)`` → single ``Question``
  • ``describe()`` → ``ClientInfo`` snapshot — no network call, no secrets

Usage (self-contained — auto-starts the fake server when no real URL is set)::

    uv run python examples/fetch_questions.py

Usage against a real server::

    AMPLIFIER_TEAM_PULSE_URL=https://your-server \\
    AMPLIFIER_TEAM_PULSE_KEY=tp_your_key \\
        uv run python examples/fetch_questions.py
"""

from __future__ import annotations

import asyncio
import os

from team_pulse_lib import TeamPulseClient
from team_pulse_lib.models import ClientInfo, Question


async def main(
    base_url: str | None = None,
    api_key: str = "tp_demo",
) -> dict:
    """Fetch active questions and print a human-readable summary.

    Args:
        base_url: Server URL.  Takes precedence over the ``AMPLIFIER_TEAM_PULSE_URL``
            env var.  If neither is set the TeamPulseClient constructor will raise.
        api_key: API key starting with ``tp_``.  Overridden by the
            ``AMPLIFIER_TEAM_PULSE_KEY`` env var when set.

    Returns:
        ``dict`` with keys ``active``, ``single``, ``all``, ``info``.
        Intended for test assertions; the function also prints a human-readable
        summary as a side effect.
    """
    url: str = base_url or os.environ.get("AMPLIFIER_TEAM_PULSE_URL") or ""
    key: str = os.environ.get("AMPLIFIER_TEAM_PULSE_KEY") or api_key

    # Recommended construction: connect() infers api-key auth from the tp_ key.
    client = TeamPulseClient.connect(base_url=url, key=key)

    print("\n=== Team Pulse: Fetch Questions ===")
    print(f"Server: {url}")

    active: list[Question]
    single: Question | None = None
    all_questions: list[Question]
    info: ClientInfo

    async with client:
        # describe() — purely local; never makes a network call, never exposes secrets
        info = await client.describe()
        print("\n[Client Info]")
        print(f"  base_url                 : {info.base_url}")
        print(f"  auth_mode                : {info.auth_mode}")
        print(f"  credential_type          : {info.credential_type}")
        print(f"  resolved                 : {info.resolved}")

        # --- fetch_questions: active only (default) ---
        active = await client.fetch_questions(status="active")
        print(f"\n[Active Questions]  ({len(active)} found)")
        for q in active:
            lb = f"{q.lookback_days}d" if q.lookback_days is not None else "no lookback"
            print(f"  [{q.question_id}]  ({lb})")
            print(f"    {q.question}")

        # --- fetch_question: single lookup by slug ---
        if active:
            slug = active[0].question_id
            single = await client.fetch_question(slug)
            print(f"\n[Single Question: fetch_question({slug!r})]")
            print(f"  question_id   : {single.question_id}")
            print(f"  question      : {single.question}")
            print(f"  lookback_days : {single.lookback_days}")

        # --- fetch_questions: all statuses ---
        all_questions = await client.fetch_questions(status="all")
        print(f"\n[All Questions (status='all')]  ({len(all_questions)} found)")
        for q in all_questions:
            print(f"  [{q.question_id}]  {q.question[:70]}")

    print("\n=== Done ===\n")
    return {"active": active, "single": single, "all": all_questions, "info": info}


if __name__ == "__main__":
    _env_url = os.environ.get("AMPLIFIER_TEAM_PULSE_URL")
    if _env_url:
        asyncio.run(main(base_url=_env_url))
    else:
        # No real server configured — spin up the stdlib-only fake server.
        from fake_team_pulse_server import FakeTeamPulseServer

        with FakeTeamPulseServer(advertise_metadata=False) as _fake_url:
            asyncio.run(main(base_url=_fake_url))
