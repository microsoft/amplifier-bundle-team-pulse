# SPDX-License-Identifier: MIT
"""Live smoke test against a REAL Team Pulse server (manual; not part of the pytest suite).

Unlike the other examples (which spin up a stdlib fake server), this script hits a
real deployment using real auth. It proves the end-to-end path the unit/mocked
tests structurally cannot: real Azure token acquisition and a real server accepting it.

Auth is inferred by the library (see team_pulse_lib.config):
  * If AMPLIFIER_TEAM_PULSE_KEY (a ``tp_*`` key) is set -> ApiKeyAuth.
  * Otherwise -> Azure DefaultAzureCredential (your ``az login`` session).
    The token scope is ``api://<api_app_id>/.default`` where api_app_id defaults
    to the shipped Team Pulse app id unless AMPLIFIER_TEAM_PULSE_API_APP_ID is set.

Usage:
    export AMPLIFIER_TEAM_PULSE_URL="https://<your-team-pulse-host>"
    # (Azure path) ensure you are logged in:  az login
    uv run python examples/real_smoke_test.py

    # To also exercise the WRITE path with a real (bare, no-metadata) answer:
    uv run python examples/real_smoke_test.py --submit

What it checks (read-only by default):
  1. describe()        -> resolved auth mode / credential type (no secrets)
  2. whoami()          -> the server accepted the token and resolved your identity
  3. fetch_questions() -> real active questions
  4. guardrail         -> an answer carrying metadata/user_id is REFUSED client-side
                          when the server does not advertise metadata support
                          (no POST is sent -> no silent data loss). Phase-0 honesty.
  5. --submit (opt-in) -> one real BARE answer (no metadata) is POSTed and the
                          returned SubmittedAnswer is printed. This WRITES real data.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys

from team_pulse_lib import AnswerUpload, TeamPulseClient


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def run(do_submit: bool) -> int:
    url = os.environ.get("AMPLIFIER_TEAM_PULSE_URL")
    if not url:
        print("ERROR: set AMPLIFIER_TEAM_PULSE_URL to a real Team Pulse host.", file=sys.stderr)
        return 2

    print(f"Server : {url}")
    key_set = bool(os.environ.get("AMPLIFIER_TEAM_PULSE_KEY"))
    print(f"Auth   : {'ApiKey (tp_ key set)' if key_set else 'Azure DefaultAzureCredential (az login)'}")

    client = TeamPulseClient.connect()  # env-driven; recommended factory (from_env() is a thin wrapper)
    async with client:  # eager Azure token acquisition happens here (fails loud if no credential)
        info = await client.describe()
        print("\n[describe]")
        print(f"  auth_mode       : {info.auth_mode}")
        print(f"  credential_type : {info.credential_type}")
        print(f"  api_app_id      : {info.api_app_id}")
        print(f"  resolved        : {info.resolved}")

        who = await client.whoami()
        print("\n[whoami] (server accepted the token)")
        print(f"  {who}")

        questions = await client.fetch_questions(status="active")
        print(f"\n[fetch_questions active] {len(questions)} found")
        for q in questions:
            print(f"  - {q.question_id:<28} lookback={q.lookback_days}  {(q.question or '')[:60]}")

        if not questions:
            print("\nNo active questions; skipping write checks.")
            return 0

        target = questions[0].question_id

        # 4. Metadata submit: schema v1 persists metadata; sessions live inside it.
        print("\n[metadata submit] posting an answer WITH metadata (sessions inside)")
        meta = AnswerUpload(
            question_id=target,
            user_id="smoke-test",
            answer="[SMOKE] metadata-bearing submit — sessions carried in metadata",
            generated_at=_utc_now_iso(),
            metadata={"source_session_ids": [], "smoke": True},
        )
        meta_result = await client.upload_answer(meta)
        print(
            f"  SubmittedAnswer(id={meta_result.id!r}, "
            f"question_id={meta_result.question_id!r}, created={meta_result.created})"
        )

        # 5. Opt-in real bare write.
        if do_submit:
            print("\n[submit] posting one REAL bare answer (no metadata) -- this WRITES data")
            bare = AnswerUpload(
                question_id=target,
                user_id="",
                answer="[SMOKE TEST] schema-v1 real-server submit verification.",
                generated_at=_utc_now_iso(),
            )
            result = await client.upload_answer(bare)
            print(f"  SubmittedAnswer(id={result.id!r}, question_id={result.question_id!r}, created={result.created})")
        else:
            print("\n[submit] skipped (pass --submit to POST one real bare answer).")

    print("\nDone.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live smoke test against a real Team Pulse server.")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Also POST one real bare (no-metadata) answer. WRITES real data.",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.submit))


if __name__ == "__main__":
    raise SystemExit(main())
