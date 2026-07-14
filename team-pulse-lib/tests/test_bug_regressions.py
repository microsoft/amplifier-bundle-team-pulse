# SPDX-License-Identifier: MIT
"""Regression tests for confirmed live-testing bugs.

BUG 1 (ship-blocking): from_env() did NOT apply the DEFAULT api_app_id on the
    Azure auth path when the user's config file contained ``api_app_id: ""`` or
    ``client_id: ""``.  The empty value satisfied the ``"api_app_id" in file_dict``
    branch in ``_resolve_settings()``, bypassing the ``DEFAULT_API_APP_ID`` fallback
    and producing scope ``api:///.default``, which Entra rejected with AADSTS500011.

    Root cause: ``config.py:_resolve_settings()``, the ``elif "api_app_id" in
    file_dict:`` branch (and its ``client_id`` sibling) did not guard against
    empty / whitespace-only values from the config file.

    Fix: treat empty/whitespace values from the config file the same as "absent" —
    fall through to the next resolution tier.  Defense-in-depth: ``AzCredentialAuth``
    now raises ``ValueError`` immediately if constructed with an empty ``api_app_id``.

BUG 2 (resource leak): ``TeamPulseClient.__aexit__`` (and ``__aenter__``
    failure paths) never called ``close()`` on the auth strategy.  For the Azure
    path, ``DefaultAzureCredential`` holds an ``aiohttp.ClientSession`` internally;
    failing to close it produced ``Unclosed client session`` warnings.

    Fix: ``AzCredentialAuth`` now exposes an async ``close()`` that delegates to
    the credential; ``TeamPulseClient`` calls ``_close_auth()`` in both ``__aexit__``
    and the ``__aenter__`` exception handlers, guarded by an idempotency flag.

BUG 3 (integration-confirmed): ``upload_answer`` returned ``id=""`` against the
    real server even though the answer was persisted with a real UUID.

    Root cause: ``client.py:upload_answer`` read ``data.get("id", "")`` from the
    top level of the 201 response, but the real server returns the answer record
    **nested** under ``"answer"``:
        ``{"answer": {"id": "<uuid>", "question_id": "...", ...}}``
    There is no top-level ``"id"`` key in the server response, so the result was
    always ``""``.

    Fix: extract the id from ``data["answer"]["id"]``, with a tolerant fallback to
    the top-level ``data.get("id", "")`` for forward-compat with any hypothetical
    flat-response shape.
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

from team_pulse_lib import config as config_mod
from team_pulse_lib.auth import AzCredentialAuth
from team_pulse_lib.client import TeamPulseClient
from team_pulse_lib.config import DEFAULT_API_APP_ID, from_env
from team_pulse_lib.errors import TeamPulseAuthError
from team_pulse_lib.models import AnswerUpload

# ---------------------------------------------------------------------------
# Shared env-var / config-dir isolation
# ---------------------------------------------------------------------------

_ENV_VARS = [
    "AMPLIFIER_TEAM_PULSE_URL",
    "AMPLIFIER_TEAM_PULSE_KEY",
    "AMPLIFIER_TEAM_PULSE_API_APP_ID",
    "AMPLIFIER_TEAM_PULSE_AUTH_MODE",
    "AMPLIFIER_TEAM_PULSE_DIR",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove all team-pulse env vars, clear deprecation guard, redirect config dir."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config_mod._WARNED_ONCE.clear()
    monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# Minimal fake credential doubles
# ---------------------------------------------------------------------------


class _FakeCred:
    """Async credential double that records get_token calls and scope used."""

    def __init__(self, token: str = "fake-token", expires_in: float = 3600.0) -> None:
        self._token = token
        self._expires_in = expires_in
        self.calls: int = 0
        self.scopes: list[str] = []
        self.closed: bool = False

    async def get_token(self, scope: str) -> SimpleNamespace:
        self.calls += 1
        self.scopes.append(scope)
        return SimpleNamespace(token=self._token, expires_on=time.time() + self._expires_in)

    async def close(self) -> None:
        self.closed = True


class _FailCred:
    """Credential double that raises on get_token (auth failure path)."""

    def __init__(self) -> None:
        self.closed: bool = False

    async def get_token(self, scope: str) -> SimpleNamespace:  # noqa: ARG002
        raise RuntimeError("no credential configured")

    async def close(self) -> None:
        self.closed = True


# ===========================================================================
# BUG 1 — DEFAULT api_app_id not applied on the Azure path
# ===========================================================================


class TestDefaultApiAppIdOnAzurePath:
    """from_env() must use DEFAULT_API_APP_ID when no api_app_id is supplied."""

    def test_no_env_no_config_uses_default_scope(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """URL set in env, no key, empty config dir → scope must contain the DEFAULT app ID."""
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
        cred = _FakeCred()
        rc = from_env(credential=cred)
        assert isinstance(rc.auth, AzCredentialAuth)
        assert rc.auth._scope == f"api://{DEFAULT_API_APP_ID}/.default", (
            f"Expected scope with DEFAULT_API_APP_ID, got {rc.auth._scope!r}"
        )
        assert rc.api_app_id == DEFAULT_API_APP_ID

    def test_config_file_empty_api_app_id_falls_through_to_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """
        BUG 1 regression: config file with ``api_app_id: ""`` must NOT bypass DEFAULT.

        Before the fix, ``_resolve_settings`` entered the ``elif "api_app_id" in file_dict``
        branch and returned ``str("") = ""``, producing scope ``api:///.default``.
        """
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
        config_file = tmp_path / "config.yaml"
        config_file.write_text('url: "https://api.example.com"\napi_app_id: ""\n', encoding="utf-8")
        # AMPLIFIER_TEAM_PULSE_DIR already points at tmp_path via _clean_env fixture

        cred = _FakeCred()
        rc = from_env(credential=cred)
        assert isinstance(rc.auth, AzCredentialAuth)
        assert rc.auth._scope == f"api://{DEFAULT_API_APP_ID}/.default", (
            f"Empty api_app_id in config must fall through to DEFAULT, got {rc.auth._scope!r}"
        )
        assert rc.api_app_id == DEFAULT_API_APP_ID

    def test_config_file_null_api_app_id_falls_through_to_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Config file with ``api_app_id: null`` (YAML null → Python None) falls through to DEFAULT."""
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
        config_file = tmp_path / "config.yaml"
        config_file.write_text("url: https://api.example.com\napi_app_id:\n", encoding="utf-8")

        cred = _FakeCred()
        rc = from_env(credential=cred)
        assert isinstance(rc.auth, AzCredentialAuth)
        assert rc.auth._scope == f"api://{DEFAULT_API_APP_ID}/.default"

    def test_config_file_empty_client_id_alias_falls_through_to_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """BUG 1 regression (client_id alias): ``client_id: ""`` must also fall through to DEFAULT."""
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
        config_file = tmp_path / "config.yaml"
        config_file.write_text('url: "https://api.example.com"\nclient_id: ""\n', encoding="utf-8")

        cred = _FakeCred()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            rc = from_env(credential=cred)
        assert isinstance(rc.auth, AzCredentialAuth)
        assert rc.auth._scope == f"api://{DEFAULT_API_APP_ID}/.default", (
            f"Empty client_id in config must fall through to DEFAULT, got {rc.auth._scope!r}"
        )

    def test_explicit_env_var_overrides_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AMPLIFIER_TEAM_PULSE_API_APP_ID env var must override the DEFAULT."""
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
        custom_id = "11111111-2222-3333-4444-555555555555"
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_API_APP_ID", custom_id)
        cred = _FakeCred()
        rc = from_env(credential=cred)
        assert isinstance(rc.auth, AzCredentialAuth)
        assert rc.auth._scope == f"api://{custom_id}/.default"
        assert rc.api_app_id == custom_id

    def test_explicit_env_var_overrides_config_file_value(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Env var takes precedence over a non-empty api_app_id in the config file."""
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_URL", "https://api.example.com")
        file_id = "aaaa-bbbb-cccc-dddd"
        env_id = "eeee-ffff-0000-1111"
        config_file = tmp_path / "config.yaml"
        config_file.write_text(f"url: https://api.example.com\napi_app_id: {file_id}\n", encoding="utf-8")
        monkeypatch.setenv("AMPLIFIER_TEAM_PULSE_API_APP_ID", env_id)
        cred = _FakeCred()
        rc = from_env(credential=cred)
        assert rc.auth._scope == f"api://{env_id}/.default", "env var must win over file value"  # type: ignore[union-attr]


# ===========================================================================
# BUG 1 defense — AzCredentialAuth.init fails loud on empty api_app_id
# ===========================================================================


class TestAzCredentialAuthEmptyAppIdFailsLoud:
    """AzCredentialAuth must raise ValueError immediately on empty/None api_app_id."""

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="api_app_id"):
            AzCredentialAuth(api_app_id="", credential=_FakeCred())

    def test_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="api_app_id"):
            AzCredentialAuth(api_app_id="   ", credential=_FakeCred())

    def test_none_raises(self) -> None:
        """Passing None violates the str type annotation; the guard catches it defensively."""
        with pytest.raises((ValueError, TypeError)):
            AzCredentialAuth(api_app_id=None, credential=_FakeCred())  # type: ignore[arg-type]

    def test_valid_app_id_does_not_raise(self) -> None:
        """A well-formed UUID-style ID must not raise."""
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=_FakeCred())
        assert auth._scope == f"api://{DEFAULT_API_APP_ID}/.default"

    def test_error_message_mentions_env_var(self) -> None:
        """Error message must mention AMPLIFIER_TEAM_PULSE_API_APP_ID so the user knows how to fix it."""
        with pytest.raises(ValueError, match="AMPLIFIER_TEAM_PULSE_API_APP_ID"):
            AzCredentialAuth(api_app_id="", credential=_FakeCred())


# ===========================================================================
# BUG 1 — scope passed to azure credential is correct
# ===========================================================================


class TestAzCredentialAuthScopePassedToCredential:
    """The scope string passed to get_token() must use the DEFAULT when no override is given."""

    @pytest.mark.asyncio
    async def test_default_scope_reaches_get_token(self) -> None:
        """The DEFAULT api_app_id scope must be passed to credential.get_token()."""
        cred = _FakeCred()
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=cred)
        await auth.headers()
        assert cred.scopes == [f"api://{DEFAULT_API_APP_ID}/.default"]

    @pytest.mark.asyncio
    async def test_custom_scope_reaches_get_token(self) -> None:
        """An explicit api_app_id must be used verbatim in the scope."""
        custom_id = "aabbccdd-1122-3344-5566-778899001122"
        cred = _FakeCred()
        auth = AzCredentialAuth(api_app_id=custom_id, credential=cred)
        await auth.headers()
        assert cred.scopes == [f"api://{custom_id}/.default"]


# ===========================================================================
# BUG 2 — DefaultAzureCredential aiohttp session leak
# ===========================================================================


class TestAzCredentialAuthClose:
    """AzCredentialAuth.close() must delegate to the underlying credential."""

    @pytest.mark.asyncio
    async def test_close_is_called_on_underlying_credential(self) -> None:
        """close() must call close() on the underlying credential."""
        cred = _FakeCred()
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=cred)
        await auth.close()
        assert cred.closed is True

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self) -> None:
        """Calling close() twice must not raise (idempotency delegated to the credential)."""
        cred = _FakeCred()
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=cred)
        await auth.close()
        await auth.close()  # must not raise


class TestClientCredentialClosedOnExit:
    """TeamPulseClient.__aexit__ must close the auth strategy to prevent resource leaks."""

    @pytest.mark.asyncio
    async def test_credential_close_called_on_successful_exit(self) -> None:
        """
        BUG 2 regression: credential.close() must be awaited when the client exits normally.

        Before the fix, __aexit__ only called http.aclose() and never closed the auth
        strategy, leaving DefaultAzureCredential's aiohttp session open.
        """
        cred = _FakeCred()
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=cred)
        client = TeamPulseClient(base_url="https://example.com", auth=auth, auth_mode="az")

        async with client:
            assert not cred.closed  # credential is open inside the context

        # After __aexit__, credential must be closed
        assert cred.closed, "__aexit__ must call close() on the AzCredentialAuth"

    @pytest.mark.asyncio
    async def test_credential_close_called_on_auth_failure_in_aenter(self) -> None:
        """
        BUG 2 regression (failure path): credential.close() must be awaited even when
        __aenter__ raises (auth failure means __aexit__ is never called by the runtime).
        """
        cred = _FailCred()
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=cred)
        client = TeamPulseClient(base_url="https://example.com", auth=auth, auth_mode="az")

        with pytest.raises(TeamPulseAuthError):
            async with client:
                pass  # should not be reached

        # Even though __aenter__ raised, credential must be closed
        assert cred.closed, "__aenter__ failure path must call close() on the credential"

    @pytest.mark.asyncio
    async def test_client_close_is_idempotent(self) -> None:
        """Calling __aexit__ twice (via _close_auth guard) must not explode."""
        cred = _FakeCred()
        auth = AzCredentialAuth(api_app_id=DEFAULT_API_APP_ID, credential=cred)
        client = TeamPulseClient(base_url="https://example.com", auth=auth, auth_mode="az")

        async with client:
            pass  # normal exit

        # Second __aexit__ call (unusual but must not raise)
        await client.__aexit__(None, None, None)
        assert cred.closed  # still closed, no error

    @pytest.mark.asyncio
    async def test_api_key_auth_close_is_noop(self) -> None:
        """ApiKeyAuth has no close(); the client must handle that gracefully (no AttributeError)."""
        from team_pulse_lib.auth import ApiKeyAuth

        auth = ApiKeyAuth("tp_fake_key_for_test")
        client = TeamPulseClient(base_url="https://example.com", auth=auth, auth_mode="key")

        async with client:
            pass  # must not raise even though ApiKeyAuth has no close() method


# ===========================================================================
# BUG 3 — upload_answer id always "" (nested response not read)
# ===========================================================================


class _SimpleApiKeyAuth:
    """Minimal auth stub for HTTP-layer tests — injects a static API key header."""

    async def headers(self) -> dict[str, str]:
        return {"X-Team-Pulse-Key": "tp_test_key"}


_BUG3_BASE_URL = "https://team-pulse.test"
_BUG3_SERVER_UUID = "aaaa1111-bbbb-2222-cccc-3333dddd4444"


class TestUploadAnswerNestedResponseId:
    """BUG 3 regression: upload_answer must read id from data['answer']['id'].

    The real server returns:
        {"answer": {"id": "<uuid>", "question_id": "...", ...}}
    NOT the flat shape the old unit-test fake used:
        {"id": "<uuid>", "question_id": "..."}

    Before the fix, data.get("id", "") returned "" because there is no top-level
    "id" key in the real 201 response.
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_upload_answer_id_extracted_from_nested_answer_key(self) -> None:
        """upload_answer must return the UUID from data['answer']['id'], not data['id'].

        RED: fails with the old client (data.get('id', '') == '').
        GREEN: passes after the fix reads data['answer']['id'].
        """
        respx.post(f"{_BUG3_BASE_URL}/api/lens/answers").mock(
            return_value=httpx.Response(
                201,
                json={"answer": {"id": _BUG3_SERVER_UUID, "question_id": "effective-practices"}},
            )
        )
        upload = AnswerUpload(
            question_id="effective-practices",
            user_id="alice",
            answer="AI synthesised answer",
            generated_at="2026-06-27T10:00:00Z",
        )
        async with TeamPulseClient(base_url=_BUG3_BASE_URL, auth=_SimpleApiKeyAuth()) as client:
            result = await client.upload_answer(upload)

        assert result.id == _BUG3_SERVER_UUID, (
            f"Expected id={_BUG3_SERVER_UUID!r} from nested 'answer.id', got {result.id!r}. "
            "Fix: read data['answer']['id'] not data['id']."
        )
        assert result.created is True
        assert result.question_id == "effective-practices"

    @pytest.mark.asyncio
    @respx.mock
    async def test_upload_answer_id_extracted_from_nested_answer_key_on_200(self) -> None:
        """Same nested read applies to idempotent 200 (already-stored answer)."""
        respx.post(f"{_BUG3_BASE_URL}/api/lens/answers").mock(
            return_value=httpx.Response(
                200,
                json={"answer": {"id": _BUG3_SERVER_UUID, "question_id": "effective-practices"}},
            )
        )
        upload = AnswerUpload(
            question_id="effective-practices",
            user_id="alice",
            answer="AI synthesised answer",
            generated_at="2026-06-27T10:00:00Z",
        )
        async with TeamPulseClient(base_url=_BUG3_BASE_URL, auth=_SimpleApiKeyAuth()) as client:
            result = await client.upload_answer(upload)

        assert result.id == _BUG3_SERVER_UUID
        assert result.created is False
