# SPDX-License-Identifier: MIT
"""TeamPulseClient — async HTTP client for the Team Pulse API.

Construction validation, pooled httpx.AsyncClient lifecycle, and eager
credential acquisition at context-manager entry.

Usage::

    async with TeamPulseClient(base_url=..., auth=...) as client:
        # _http is active, credential already validated
        ...
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Literal

import httpx

from team_pulse_lib.auth import AzCredentialAuth
from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
)
from team_pulse_lib.models import AnswerUpload, ClientInfo, Question, SubmittedAnswer

# ---------------------------------------------------------------------------
# Module-level sentinels
# ---------------------------------------------------------------------------

_NO_CONTEXT_MSG: str = "TeamPulseClient must be used inside 'async with client:' before making requests"

# Sentinel for detecting "auth_mode not explicitly passed" in __init__.
# Using object() avoids any accidental truthiness match.
_UNSET: object = object()


def _server_error_message(body: str) -> str:
    """Extract the server's ``{"error": {"message": ...}}`` detail, if present.

    Returns a `" Server said: <message>"` suffix so an auth failure surfaces the
    server's *actionable* message (e.g. ``bearer_required`` on the bulk corpus
    endpoint: "a shared API key cannot attribute a bulk pull to a specific
    member") instead of only the generic client-side hint. Returns "" when the
    body is absent or not the structured-error shape.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return ""
    err = parsed.get("error") if isinstance(parsed, dict) else None
    msg = err.get("message") if isinstance(err, dict) else None
    return f" Server said: {msg}" if isinstance(msg, str) and msg else ""


def _extract_zip_safely(data: bytes, dest: Path) -> int:
    """Extract a corpus zip into *dest*, guarding against zip-slip.

    Returns the number of files written. Any member whose resolved path would
    escape *dest* (absolute path or ``..`` traversal) is skipped rather than
    written — the server only ever emits sandboxed ``corpus/<...>`` ids, so this
    is belt-and-braces defence for an untrusted archive.
    """
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = (dest / member.filename).resolve()
            if target != dest and dest not in target.parents:
                # zip-slip attempt — refuse to write outside dest.
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                out.write(src.read())
            written += 1
    return written


# ---------------------------------------------------------------------------
# TeamPulseClient
# ---------------------------------------------------------------------------


class TeamPulseClient:
    """Async HTTP client for the Team Pulse API.

    Must be used as an async context manager.  The credential is validated
    **eagerly** at ``__aenter__`` — never mid-request — so failures surface
    at a clean boundary and are always wrapped as :exc:`TeamPulseAuthError`.

    Args:
        base_url: Team Pulse server URL.  Required; raises :exc:`ValueError`
            if falsy.  Trailing slashes are stripped.
        auth: Any object satisfying the :class:`~team_pulse_lib.auth.AuthStrategy`
            protocol (``async def headers() -> dict[str, str]``).
        timeout: HTTP timeout in seconds (default ``30.0``).
        auth_mode: Provenance field from :class:`~team_pulse_lib.config.ResolvedConfig`.
            Defaults to ``'key'``.
        api_app_id: Provenance field — Azure AD app ID used when ``auth_mode='az'``.
        forced: Provenance field — ``True`` when the strategy was pinned by the caller.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth: Any,
        timeout: float = 30.0,
        auth_mode: Any = _UNSET,  # Literal["key", "az"] when supplied explicitly
        api_app_id: str | None = None,
        forced: bool = False,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self._base_url: str = base_url.rstrip("/")
        self._auth: Any = auth
        self._timeout: float = timeout

        # Provenance — type-based inference when auth_mode is not explicitly supplied.
        # This is TYPE INSPECTION ONLY: no env reads, no IO, no auth inference policy.
        # Factories (connect / from_env / from_config) always supply auth_mode from
        # ResolvedConfig, so inference only fires for direct __init__ construction.
        if auth_mode is _UNSET:
            auth_mode = "az" if isinstance(auth, AzCredentialAuth) else "key"
        self._auth_mode: Literal["key", "az"] = auth_mode  # type: ignore[assignment]

        # Infer api_app_id from AzCredentialAuth instance when not explicitly passed.
        # Only triggered for direct __init__ construction (factories supply it from RC).
        if api_app_id is None and isinstance(auth, AzCredentialAuth):
            api_app_id = auth.api_app_id
        self._api_app_id: str | None = api_app_id

        self._forced: bool = forced
        # Lifecycle state
        self._http: httpx.AsyncClient | None = None
        self._resolved: bool = False
        self._auth_closed: bool = False  # guard against double-close

    # ------------------------------------------------------------------
    # Factory classmethods
    # ------------------------------------------------------------------

    @classmethod
    def connect(
        cls,
        *,
        base_url: str | None = None,
        key: str | None = None,
        force: str | None = None,
        timeout: float = 30.0,
    ) -> "TeamPulseClient":
        """Blessed factory: one call gives "url in code, app id defaulted, auth inferred".

        This is the **single resolution home**: all precedence rules, auth
        inference, and provenance labelling live in
        :func:`team_pulse_lib.config.from_args`.  ``from_env`` and
        ``from_config`` are thin wrappers over this path.

        Precedence (high → low):

        1. Explicit arg (``base_url``, ``key``)
        2. ``AMPLIFIER_TEAM_PULSE_URL`` / ``AMPLIFIER_TEAM_PULSE_KEY`` env var
        3. ``~/.amplifier/team-pulse/config.yaml``
        4. Shipped default (``api_app_id`` only → ``DEFAULT_API_APP_ID``)

        Args:
            base_url: Team Pulse server URL.  When provided, wins over env/file.
                ``None`` means "not supplied — fall through to env/file".
            key: API key override.  When provided and ``tp_``-prefixed, selects
                ``ApiKeyAuth``.  ``None`` means "not supplied — use env/file".
            force: Pin to ``'key'`` or ``'az'`` exactly; raises ``ValueError``
                for any other value.
            timeout: HTTP timeout in seconds (default ``30.0``).
        """
        from . import config  # local import keeps the module import graph lean

        rc = config.from_args(base_url=base_url, key=key, force=force)
        return cls(
            base_url=rc.base_url,
            auth=rc.auth,
            timeout=timeout,
            auth_mode=rc.auth_mode,
            api_app_id=rc.api_app_id,
            forced=rc.forced,
        )

    @classmethod
    def from_env(cls, *, force: str | None = None, timeout: float = 30.0) -> "TeamPulseClient":
        """Construct a client purely from the environment and user config file.

        Thin wrapper over :meth:`connect` — equivalent to
        ``connect(force=force, timeout=timeout)`` with no in-code URL or key.
        All resolution (env vars, ``~/.amplifier/team-pulse/config.yaml``,
        defaults) is performed by :func:`team_pulse_lib.config.from_args`.

        .. note::
            ``from_env`` intentionally has **no** ``base_url`` parameter.  A
            factory named ``from_env`` that accepts an in-code URL would be a
            naming lie.  Use :meth:`connect` when you want to supply a URL in
            code.

        Args:
            force: Pin to ``'key'`` or ``'az'`` exactly.
            timeout: HTTP timeout in seconds (default ``30.0``).
        """
        return cls.connect(force=force, timeout=timeout)

    @classmethod
    def from_config(
        cls,
        path: "str | Any",
        *,
        force: str | None = None,
        timeout: float = 30.0,
    ) -> "TeamPulseClient":
        """Construct a client by resolving configuration from a YAML file.

        Thin wrapper: delegates to :func:`team_pulse_lib.config.from_config`
        for all resolution, inference, and provenance.  Provenance fields are
        carried from :class:`~team_pulse_lib.config.ResolvedConfig` without
        re-derivation.

        Args:
            path: Path to a YAML config file (``str`` or :class:`pathlib.Path`).
            force: Pin to ``'key'`` or ``'az'`` exactly.
            timeout: HTTP timeout in seconds (default ``30.0``).
        """
        from . import config  # local import keeps the module import graph lean

        rc = config.from_config(path, force=force)
        return cls(
            base_url=rc.base_url,
            auth=rc.auth,
            timeout=timeout,
            auth_mode=rc.auth_mode,
            api_app_id=rc.api_app_id,
            forced=rc.forced,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def _credential_type(self) -> str:
        """Return the provenance label for the credential strategy in use."""
        return "azure_default_credential" if self._auth_mode == "az" else "api_key"

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "TeamPulseClient":
        http = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        try:
            # Eagerly acquire credential at context boundary — never mid-request.
            # Uniform: never branches on auth strategy; always calls headers().
            await self._auth.headers()
        except TeamPulseAuthError:
            await http.aclose()
            self._http = None
            await self._close_auth()  # release credential resources (e.g. AzCredentialAuth aiohttp session)
            raise
        except Exception as exc:  # noqa: BLE001
            await http.aclose()
            self._http = None
            await self._close_auth()  # release credential resources on unexpected failure
            raise TeamPulseAuthError(
                "Could not acquire a Team Pulse credential. "
                "For Azure, run `az login` or set AZURE_CLIENT_ID / a managed identity; "
                "for key auth, set AMPLIFIER_TEAM_PULSE_KEY. "
                f"Underlying error: {exc}"
            ) from exc
        self._http = http
        self._resolved = True
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        await self._close_auth()

    async def _close_auth(self) -> None:
        """Close the auth strategy if it exposes a ``close()`` method.

        Idempotent \u2014 safe to call from both ``__aexit__`` (success path) and
        ``__aenter__`` failure handlers (so a failed credential acquisition never
        leaks an open ``aiohttp.ClientSession`` inside DefaultAzureCredential).
        """
        if self._auth_closed:
            return
        self._auth_closed = True
        close_fn = getattr(self._auth, "close", None)
        if callable(close_fn):
            try:
                await close_fn()  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                pass  # best-effort: never mask the caller's original exception

    # ------------------------------------------------------------------
    # Internal guards
    # ------------------------------------------------------------------

    def _require_http(self) -> httpx.AsyncClient:
        """Return the active HTTP client, or raise :exc:`RuntimeError` if outside context.

        Raises:
            RuntimeError: When called outside an ``async with`` block.
        """
        if self._http is None:
            raise RuntimeError(_NO_CONTEXT_MSG)
        return self._http

    # ------------------------------------------------------------------
    # HTTP helpers — typed error mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _best_effort_body(resp: httpx.Response) -> str:
        """Return the response body as text, or empty string if decoding fails."""
        try:
            return resp.text
        except Exception:  # noqa: BLE001 — body decode must never mask the API error
            return ""

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Make an authenticated request, mapping failures to the typed exception family.

        Raises:
            TeamPulseConnectionError: Transport-level failure (DNS, refused, timeout).
            TeamPulseAuthError: HTTP 401 or 403 from the server.
            TeamPulseAPIError: Any other non-2xx HTTP response.
        """
        http = self._require_http()
        headers = {"Accept": "application/json", **await self._auth.headers()}
        try:
            resp = await http.request(method, path, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            raise TeamPulseConnectionError(f"Could not reach Team Pulse at {self._base_url}{path}: {exc}") from exc
        if resp.status_code in (401, 403):
            server_msg = _server_error_message(self._best_effort_body(resp))
            raise TeamPulseAuthError(
                f"Team Pulse rejected the credential (HTTP {resp.status_code}) for {path}. "
                f"Check the API key or Azure identity authorization.{server_msg}"
            )
        if resp.status_code >= 400:
            raise TeamPulseAPIError(status=resp.status_code, body=self._best_effort_body(resp))
        return resp

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Issue an authenticated GET request."""
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, json_body: Any) -> httpx.Response:
        """Issue an authenticated POST request with a JSON body."""
        return await self._request("POST", path, json=json_body)

    # ------------------------------------------------------------------
    # Envelope normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_list_envelope(body: Any) -> dict[str, Any]:
        """Return a guaranteed {count: int, resources: list} dict.

        Non-dict body yields the empty envelope.  Missing or wrong-typed
        ``resources`` / ``count`` fields are fixed up in-place so callers
        always receive a well-formed envelope.
        """
        if not isinstance(body, dict):
            return {"count": 0, "resources": []}
        resources = body.get("resources")
        if not isinstance(resources, list):
            resources = []
        count = body.get("count")
        if not isinstance(count, int):
            count = len(resources)
        return {"count": count, "resources": resources}

    # ------------------------------------------------------------------
    # Generic lens reads
    # ------------------------------------------------------------------

    async def describe(self) -> ClientInfo:
        """Return a provenance-only snapshot of the resolved client configuration.

        **Never makes a network call; never exposes secrets.**  Safe to call at
        any point — before or after entering the async context manager.
        """
        return ClientInfo(
            base_url=self._base_url,
            auth_mode=self._auth_mode,
            api_app_id=self._api_app_id,
            credential_type=self._credential_type,
            forced=self._forced,
            resolved=self._resolved,
            identity_hint=(
                self._auth.identity_hint if isinstance(self._auth, AzCredentialAuth) else None
            ),
        )

    async def info(self) -> Any:
        """GET /api/lens/info — return the server's self-description."""
        resp = await self._get("/api/lens/info")
        return resp.json()

    async def resources(
        self,
        type: str | None = None,  # noqa: A002
        collection: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/lens/resources — list resources, optionally filtered.

        Args:
            type: Resource type filter (e.g. ``'project'``).  Omitted when falsy.
            collection: Collection name filter.  Omitted when falsy.
            status: Lifecycle filter for ``type='question'`` — ``'active'``
                (server default), ``'archived'``, or ``'all'``.  Omitted when
                falsy (server then applies its active-only default).  The server
                ignores it for non-question types.
        """
        params: dict[str, str] = {}
        if type:
            params["type"] = type
        if collection:
            params["collection"] = collection
        if status:
            params["status"] = status
        resp = await self._get("/api/lens/resources", params=params or None)
        return self._normalize_list_envelope(resp.json())

    async def get(self, resource_id: str) -> Any:
        """GET /api/lens/resources/{resource_id} — fetch a single resource.

        Args:
            resource_id: Full resource ID (e.g. ``'projects/team-pulse'``).
                Leading slashes are stripped so both forms are accepted.

        Raises:
            ValueError: When *resource_id* is falsy.
        """
        if not resource_id:
            raise ValueError("resource_id is required")
        path = f"/api/lens/resources/{resource_id.lstrip('/')}"
        resp = await self._get(path)
        return resp.json()

    async def graph(self) -> Any:
        """GET /api/lens/graph — return the full entity graph."""
        resp = await self._get("/api/lens/graph")
        return resp.json()

    async def whoami(self) -> Any:
        """GET /api/lens/me — resolve the caller's identity."""
        resp = await self._get("/api/lens/me")
        return resp.json()

    async def search(
        self,
        q: str,
        limit: int = 50,
        collection: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/lens/resources/search — search resources by query string.

        Args:
            q: Search query.  Required; raises :exc:`ValueError` if falsy.
            limit: Max results (default ``50``).
            collection: Content collection name.  Omitted when falsy.

        Raises:
            ValueError: When *q* is falsy.
        """
        if not q:
            raise ValueError("q is required")
        params: dict[str, Any] = {"q": q, "limit": limit}
        if collection:
            params["collection"] = collection
        resp = await self._get("/api/lens/resources/search", params=params)
        return self._normalize_list_envelope(resp.json())

    async def prefix(self, prefix: str) -> dict[str, Any]:
        """GET /api/lens/resources/prefix/{prefix} — list resources by ID prefix.

        Args:
            prefix: ID prefix (e.g. ``'projects'``).  Required; raises
                :exc:`ValueError` if falsy.  Leading slashes are stripped.

        Raises:
            ValueError: When *prefix* is falsy.
        """
        if not prefix:
            raise ValueError("prefix is required")
        path = f"/api/lens/resources/prefix/{prefix.lstrip('/')}"
        resp = await self._get(path)
        return self._normalize_list_envelope(resp.json())

    async def ask(self, prompt: str, focus: str | None = None) -> Any:
        """POST /api/lens/ask — ask the Team Pulse LLM a question.

        Args:
            prompt: The question to ask.  Required.
            focus: Optional lens resource ID used as orientation hint.
                Omitted from the request body when ``None``.

        Returns:
            Raw dict with ``content``, ``prompt_used``, and ``provenance``.
        """
        body: dict[str, Any] = {"prompt": prompt}
        if focus is not None:
            body["focus"] = focus
        resp = await self._post("/api/lens/ask", json_body=body)
        return resp.json()

    # ------------------------------------------------------------------
    # Bulk corpus download
    # ------------------------------------------------------------------

    async def download_corpus(
        self,
        dest_dir: str | Path,
        folder: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/lens/corpus/download — pull the corpus as a zip to disk.

        This is the ONLY bulk method: every other client call returns a single
        JSON payload, whereas this fetches a binary zip of the mined corpus
        (conversation wikis + repo-weaver code wikis) and extracts it under
        *dest_dir*.  It returns a provenance SUMMARY only — never the page
        bodies — so a caller (or agent) can pull hundreds of files without
        loading any of them into memory/context.

        The endpoint is bearer-only on the server (Door 2): a shared API key is
        refused (403), because a bulk pull must be attributable to a member.

        Args:
            dest_dir: Local directory to extract into (created if absent).
            folder: Optional sub-corpus narrow (an id-prefix). Sub-corpus names
                are instance-specific — discover them via ``info()``
                (``collections[].sub_corpora``); an unknown name yields an empty
                result. Omit for the whole corpus.

        Returns:
            ``{written: int, dest_dir: str, folder: str | None, bytes: int}``.

        Raises:
            TeamPulseAuthError: 401/403 (shared key refused, or non-member).
            TeamPulseAPIError: Any other non-2xx response.
        """
        params = {"folder": folder} if folder else None
        resp = await self._get("/api/lens/corpus/download", params=params)
        data = resp.content
        dest = Path(dest_dir)
        written = _extract_zip_safely(data, dest)
        return {
            "written": written,
            "dest_dir": str(dest),
            "folder": folder,
            "bytes": len(data),
        }

    # ------------------------------------------------------------------
    # Typed question reads
    # ------------------------------------------------------------------

    @staticmethod
    def _question_from_resource(resource: Any) -> Question:
        """Convert a raw resource envelope dict into a :class:`Question` dataclass.

        Handles missing or malformed data defensively: a non-dict resource is
        treated as an empty dict, and a missing ``lookback_days`` field returns
        ``None`` without raising ``KeyError``.
        """
        if not isinstance(resource, dict):
            resource = {}
        data = resource.get("data")
        if not isinstance(data, dict):
            data = {}
        qid = data.get("id")
        if not qid:
            envelope_id = str(resource.get("id", ""))
            qid = envelope_id.split("/", 1)[-1] if envelope_id else ""
        return Question(
            question_id=str(qid),
            question=str(data.get("question", "")),
            lookback_days=data.get("lookback_days"),
        )

    async def fetch_questions(self, status: str = "active") -> list[Question]:
        """GET /api/lens/resources?type=question&status=<status> — typed :class:`Question`.

        The ``status`` filter is sent to the server, which applies it
        authoritatively (archived questions are only returned for
        ``'archived'``/``'all'``). It is ALSO re-applied client-side as a
        defensive fallback, so an older server that ignores the query param still
        yields the correct set for the default ``'active'`` case.

        Args:
            status: One of ``'active'`` (default), ``'archived'``, or ``'all'``.
                ``'all'`` returns every question regardless of status.
        """
        resp = await self._get(
            "/api/lens/resources", params={"type": "question", "status": status}
        )
        body = resp.json()
        resources = body.get("resources") if isinstance(body, dict) else None
        if not isinstance(resources, list):
            resources = []
        result: list[Question] = []
        for res in resources:
            if not isinstance(res, dict):
                continue
            data = res.get("data")
            if not isinstance(data, dict):
                data = {}
            res_status = data.get("status", "active")
            if status != "all" and res_status != status:
                continue
            result.append(self._question_from_resource(res))
        return result

    async def fetch_question(self, question_id: str) -> Question:
        """GET /api/lens/resources/questions/{question_id} — fetch a single question.

        Args:
            question_id: Bare question slug (e.g. ``'higher-level-work'``).
        """
        resp = await self._get(f"/api/lens/resources/questions/{question_id}")
        return self._question_from_resource(resp.json())

    # ------------------------------------------------------------------
    # Answer submission
    # ------------------------------------------------------------------

    async def upload_answer(self, answer: AnswerUpload) -> SubmittedAnswer:
        """POST /api/lens/answers — submit an AI-synthesised answer.

        Sends the partner's canonical wire body **exactly**::

            {question_id, user_id, generated_at, answer, metadata}

        ``metadata`` is ALWAYS present (an empty dict when the caller supplied
        none); session provenance lives **inside** it.  There is no ``source``
        wire field and no capability guardrail — the server persists metadata
        as of schema v1, and deploy-server-first removes the silent-loss window.

        Returns a :class:`SubmittedAnswer` with ``created=True`` on a 201
        (newly created) and ``created=False`` on an idempotent 200.

        Args:
            answer: Populated :class:`AnswerUpload` dataclass.
        """
        body: dict[str, Any] = {
            "question_id": answer.question_id,
            "user_id": answer.user_id,
            "generated_at": answer.generated_at,
            "answer": answer.answer,
            "metadata": answer.metadata,
        }

        resp = await self._post("/api/lens/answers", json_body=body)
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict):
            data = {}

        # The real server nests the persisted record under "answer":
        #   {"answer": {"id": "<uuid>", "question_id": "...", ...}}
        # Read from there first; fall back to the top level for tolerance.
        answer_data = data.get("answer", {})
        if not isinstance(answer_data, dict):
            answer_data = {}
        return SubmittedAnswer(
            id=str(answer_data.get("id", data.get("id", ""))),
            question_id=str(answer_data.get("question_id", data.get("question_id", answer.question_id))),
            created=(resp.status_code == 201),
        )
