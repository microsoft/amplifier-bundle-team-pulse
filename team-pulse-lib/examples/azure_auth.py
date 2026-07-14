# SPDX-License-Identifier: MIT
"""Construction + provenance demo for TeamPulseClient.connect() (no Azure, no network).

WHAT THIS SCRIPT DOES
    Demonstrates the four CONSTRUCTION FORMS of TeamPulseClient and prints each
    one's resolved provenance via describe() -- auth_mode, credential_type,
    api_app_id, base_url, resolved.

WHAT IT DOES *NOT* DO
    It does NOT acquire a real Azure token and does NOT make any network call.
    Constructing a client is pure local resolution; only `async with client:`
    (__aenter__) eagerly acquires the Azure token. describe() reads LOCAL
    resolved state only, so this script runs clean with:
        * no `az login`
        * no network access
        * no AMPLIFIER_TEAM_PULSE_* config on disk

    That is exactly why it is safe to run anywhere: it proves the wiring
    (which strategy is selected, what audience/app-id is used, what the
    provenance labels report) without touching Azure or a server.

TO MAKE REAL CALLS WITH AZURE
    1. `az login`
    2. point AMPLIFIER_TEAM_PULSE_URL at a real Team Pulse deployment
    3. run `uv run python examples/real_smoke_test.py`
       (that script enters the context, so it acquires a real token and hits
       the live server).

RUN
    uv run python examples/azure_auth.py
"""

from __future__ import annotations

import asyncio
import os

from team_pulse_lib import DEFAULT_API_APP_ID, AzCredentialAuth, TeamPulseClient


async def _show(label: str, note: str, client: TeamPulseClient) -> None:
    """Print a labeled provenance block for *client* via describe() (no network)."""
    info = await client.describe()
    print(f"=== {label} ===")
    print(f"  {note}")
    print(f"  base_url        : {info.base_url}")
    print(f"  auth_mode       : {info.auth_mode}")
    print(f"  credential_type : {info.credential_type}")
    print(f"  api_app_id      : {info.api_app_id}")
    print(f"  resolved        : {info.resolved}  (False = context not entered; no token acquired)")
    print()


async def main() -> None:
    print("TeamPulseClient construction + provenance demo")
    print("(no az login, no network -- describe() reads local resolved state only)")
    print(f"Shipped default app id (audience): {DEFAULT_API_APP_ID}")
    print()

    # -- 1. HEADLINE: url in code, app id defaulted, Azure inferred ----------
    # No key is supplied, so the key-wins rule selects Azure. The audience
    # (api_app_id) defaults to the service-owned DEFAULT_API_APP_ID. This is
    # the single recommended form for a consumer pointing at the canonical
    # deployment: set only the URL.
    headline = TeamPulseClient.connect(base_url="https://my-deployment.example.com")
    await _show(
        "1. HEADLINE -- connect(base_url=...)",
        "url in code; no key -> Azure inferred; app id defaulted",
        headline,
    )

    # -- 2. ENV-DRIVEN (12-factor): what a headless service uses -------------
    # A deployed/headless service sets AMPLIFIER_TEAM_PULSE_URL in its real
    # environment and calls connect() (or from_env()) with no args. Here we
    # set the env var temporarily so the demo is self-contained; in production
    # this comes from the actual process environment, not os.environ writes.
    os.environ["AMPLIFIER_TEAM_PULSE_URL"] = "https://env-driven.example.com"
    try:
        env_client = TeamPulseClient.connect()  # equivalent: TeamPulseClient.from_env()
        await _show(
            "2. ENV-DRIVEN -- connect()  (a.k.a. from_env())",
            "no args; reads AMPLIFIER_TEAM_PULSE_URL from the environment (12-factor)",
            env_client,
        )
    finally:
        del os.environ["AMPLIFIER_TEAM_PULSE_URL"]

    # -- 3. API-KEY form (for contrast) -------------------------------------
    # A tp_-prefixed key flips the inference to ApiKeyAuth. No Azure involved.
    key_client = TeamPulseClient.connect(
        base_url="https://my-deployment.example.com",
        key="tp_demo",  # demo placeholder; never a real secret in source
    )
    await _show(
        "3. API-KEY -- connect(base_url=..., key='tp_...')",
        "tp_-prefixed key -> ApiKeyAuth selected (auth_mode='key')",
        key_client,
    )

    # -- 4. ADVANCED: explicit override for a different deployment's audience -
    # The raw __init__ is the escape hatch. Pass an AzCredentialAuth with a
    # DIFFERENT api_app_id when targeting a deployment whose Entra audience is
    # not the shipped default. Provenance is now correct: describe() reports
    # auth_mode='az' (the direct-construction mislabel was fixed).
    advanced = TeamPulseClient(
        base_url="https://other-deployment.example.com",
        auth=AzCredentialAuth(api_app_id="11111111-2222-3333-4444-555555555555"),
    )
    await _show(
        "4. ADVANCED -- TeamPulseClient(base_url=..., auth=AzCredentialAuth(api_app_id=...))",
        "explicit override for a different deployment's audience; provenance correct after the fix",
        advanced,
    )

    print("Demo complete. No Azure token was acquired and no network call was made.")
    print("For a REAL Azure round-trip: az login, set AMPLIFIER_TEAM_PULSE_URL,")
    print("then run examples/real_smoke_test.py.")


if __name__ == "__main__":
    asyncio.run(main())
