# SPDX-License-Identifier: MIT
"""Authentication strategies for TeamPulseClient.

TeamPulseClient in Phase 0B depends only on the AuthStrategy protocol; it never
branches on a concrete strategy.  Two implementations are provided:

* ApiKeyAuth — attaches the API key via the ``X-Team-Pulse-Key`` request header.
* AzCredentialAuth — attaches an Azure AD bearer token via the ``Authorization``
  header (added in Task 5).
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from team_pulse_lib.errors import TeamPulseAuthError


@runtime_checkable
class AuthStrategy(Protocol):
    """Minimal protocol every authentication strategy must satisfy."""

    async def headers(self) -> dict[str, str]: ...


def is_valid_key(key: str | None) -> bool:
    """N1 rule: a key is 'present' iff non-empty after strip AND prefixed 'tp_'.

    Anything else (empty, whitespace-only, or not tp_-prefixed) is treated as
    absent (= 'malformed') and triggers Azure fallback.
    """
    if not key:
        return False
    stripped = key.strip()
    return bool(stripped) and stripped.startswith("tp_")


class ApiKeyAuth:
    """Authentication via a static API key in the ``X-Team-Pulse-Key`` header."""

    def __init__(self, key: str | None) -> None:
        if not is_valid_key(key):
            raise TeamPulseAuthError("API key missing or malformed: it must be non-empty and start with 'tp_'.")
        assert key is not None
        self._key = key.strip()

    async def headers(self) -> dict[str, str]:
        return {"X-Team-Pulse-Key": self._key}


# ---------------------------------------------------------------------------
# Azure credential factory — single seam for test/prod injection (must-fix 3)
# ---------------------------------------------------------------------------


def _build_credential(credential: Any | None = None) -> Any:
    """Return *credential* verbatim if provided; otherwise construct DefaultAzureCredential.

    This factory is the single seam that lets tests inject a fake credential while
    production code always gets the real DefaultAzureCredential chain.  The raw
    DefaultAzureCredential is never constructed outside this function so that the
    resolution chain (env vars, managed identity, az CLI, …) never runs during tests.
    """
    if credential is not None:
        return credential
    from azure.identity.aio import DefaultAzureCredential  # noqa: PLC0415

    return DefaultAzureCredential()


# ---------------------------------------------------------------------------
# AzCredentialAuth — Azure AD bearer-token strategy
# ---------------------------------------------------------------------------


class AzCredentialAuth:
    """Emits ``Authorization: Bearer <token>`` via azure-identity.

    Replaces the legacy ``AzTokenAuth`` (az CLI subprocess).  Tokens are acquired
    lazily on the first ``headers()`` call and cached until within ``_SKEW_SECONDS``
    of their reported expiry.  Phase 0B acquires eagerly at ``__aenter__`` by calling
    ``headers()`` once before the session starts.
    """

    _SKEW_SECONDS = 300

    def __init__(self, *, api_app_id: str, credential: Any | None = None) -> None:
        # Fail loud immediately — an empty api_app_id builds scope "api:///.default"
        # which Entra rejects with AADSTS500011.  Callers must supply the real ID
        # (e.g. via AMPLIFIER_TEAM_PULSE_API_APP_ID) or rely on the shipped default
        # in team_pulse_lib.config (DEFAULT_API_APP_ID).
        if not api_app_id or not str(api_app_id).strip():
            raise ValueError(
                "AzCredentialAuth requires a non-empty api_app_id. "
                "An empty value would produce scope 'api:///.default' which Entra rejects "
                "(AADSTS500011). Set AMPLIFIER_TEAM_PULSE_API_APP_ID or 'api_app_id' in "
                "your config file, or rely on the shipped default "
                "(dea6e881-4cd8-4aba-87da-a52ff3e19bce)."
            )
        self._api_app_id = str(api_app_id).strip()
        self._scope = f"api://{self._api_app_id}/.default"
        self._credential = _build_credential(credential)
        self._token: str | None = None
        self._expires_at: float = 0.0

    @property
    def api_app_id(self) -> str:
        """Read-only: the Azure AD application ID used for scope construction."""
        return self._api_app_id

    async def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._get_token()}"}

    async def close(self) -> None:
        """Close the underlying Azure credential to release its aiohttp session.

        ``azure.identity.aio.DefaultAzureCredential`` holds an ``aiohttp.ClientSession``
        internally.  Failing to call ``close()`` produces ``Unclosed client session``
        warnings at process exit.  This method is idempotent \u2014 safe to call multiple times.
        """
        if hasattr(self._credential, "close"):
            await self._credential.close()

    async def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._expires_at - self._SKEW_SECONDS:
            return self._token
        try:
            access = await self._credential.get_token(self._scope)
        except Exception as exc:  # noqa: BLE001
            raise TeamPulseAuthError(
                f"No Azure credential available — run `az login` or set AZURE_CLIENT_ID/"
                f"AZURE_TENANT_ID/AZURE_CLIENT_SECRET. Underlying error: {exc}"
            ) from exc
        token_str: str = access.token
        self._token = token_str
        self._expires_at = float(access.expires_on)
        return token_str
