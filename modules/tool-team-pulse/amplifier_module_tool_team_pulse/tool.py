# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Thin adapter over team_pulse_lib — tool entry point for Amplifier.

This module is the team-pulse Amplifier tool module.  It wraps ``team_pulse_lib``
(the standalone async client library) and exposes its capabilities as Amplifier
tools via ``mount()``.

All concrete tool classes are implemented here.  See ``_DATA_TOOL_CLASSES`` for
the ordered list of data tools and ``mount()`` for the Amplifier entry point.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Awaitable, Callable

from team_pulse_lib import (
    AnswerUpload,
    TeamPulseAPIError,
    TeamPulseClient,
    TeamPulseConnectionError,
    TeamPulseError,
)
from team_pulse_lib import config as tpl_config

logger = logging.getLogger(__name__)

__amplifier_module_type__ = "tool"


# --- ToolResult compatibility shim ---------------------------------------
# Tool modules run inside the host process (which already has amplifier_core
# loaded) but tests may run in isolation.  Mirror the modes-bundle pattern:
# import the real type if available, fall back to a minimal local stand-in.

try:
    from amplifier_core import ToolResult  # type: ignore[assignment]
except ImportError:

    class ToolResult:  # type: ignore[no-redef]
        def __init__(
            self,
            success: bool = True,
            output: Any = None,
            error: dict[str, Any] | None = None,
        ):
            self.success = success
            self.output = output
            self.error = error

        def __str__(self) -> str:
            return str(self.error) if self.error else str(self.output or "")


# --- Cached client provider ----------------------------------------------


class _ClientProvider:
    """Cached, lazily-built async-context-entered provider for TeamPulseClient.

    On the first call to :meth:`client`, the ``build`` callable is awaited and
    the returned client's async context is entered exactly once.  Subsequent
    calls return the same cached instance.  An :class:`asyncio.Lock` with a
    double-check pattern guards the build step so concurrent coroutines cannot
    trigger more than one build.

    :meth:`aclose` exits the client's async context and is idempotent — safe
    to call multiple times (only the first call exits the context; further
    calls are no-ops).  Calling :meth:`aclose` before :meth:`client` has ever
    been called is also a no-op.

    :meth:`reset` closes the current client so that the next :meth:`client`
    call triggers a fresh build.
    """

    def __init__(self, build: Callable[[], Awaitable[TeamPulseClient]]) -> None:
        self._build = build
        self._client: TeamPulseClient | None = None
        self._lock = asyncio.Lock()

    async def client(self) -> TeamPulseClient:
        """Return the cached client, building and entering its context if needed."""
        # Fast path: already built.
        if self._client is not None:
            return self._client
        async with self._lock:
            # Double-check after acquiring the lock — another coroutine may
            # have completed the build while we were waiting.
            if self._client is not None:
                return self._client
            c = await self._build()
            await c.__aenter__()
            self._client = c
        return self._client

    async def aclose(self) -> None:
        """Exit the client's async context.  Idempotent — safe to call multiple times."""
        async with self._lock:
            if self._client is None:
                return
            c = self._client
            # Clear the reference first so a concurrent client() call that
            # arrives between the clear and __aexit__ will trigger a rebuild
            # rather than using a half-closed client.
            self._client = None
            await c.__aexit__(None, None, None)

    async def reset(self) -> None:
        """Close the current client; the next :meth:`client` call will rebuild."""
        await self.aclose()


# --- Error translation helpers -------------------------------------------


#: Envelope returned when the tool cannot be reached because the endpoint
#: URL is not configured.  Code "not_configured" is a well-known sentinel
#: value that callers (e.g. the mode) can branch on to surface a helpful
#: "please run team_pulse_configure" message instead of a raw error.
_NOT_CONFIGURED_ERROR: dict[str, Any] = {
    "code": "not_configured",
    "message": (
        "Team Pulse endpoint URL is not configured. Use the team_pulse_configure tool to set the URL and credentials."
    ),
    "status": 400,
}


def _error_result(exc: Exception) -> "ToolResult":
    """Translate any exception raised by a tool's _call() into a ToolResult.

    Translation table (checked in order):

    1. Any exception with a non-None ``.envelope`` dict attribute — the
       envelope is passed through verbatim.  This covers the legacy
       ``amplifier_module_tool_team_pulse.client.TeamPulseAPIError`` which
       carries the lens API error envelope directly.

    2. ``team_pulse_lib.TeamPulseAPIError`` (new-lib style, no ``.envelope``)
       → ``{code: 'api_error', message, status}``.

    3. ``TeamPulseConnectionError`` → ``{code: 'transport_error', status: 0}``.

    4. ``TeamPulseError`` (any remaining base-class instance)
       → ``{code: 'team_pulse_error', status: 0}``.

    5. Anything else (including ``ValueError`` and its subclasses such as
       ``AzTokenError``) → ``{code: getattr(exc, 'code', 'invalid_argument'),
       status: getattr(exc, 'status', 400)}``.  Subclasses of ``ValueError``
       that carry their own ``.code`` / ``.status`` (e.g. ``AzTokenError``)
       therefore propagate their specific codes without special-casing.
    """
    # 1. Duck-type envelope: any exception that has a dict .envelope uses it
    #    directly.  This preserves the lens API error envelope verbatim so
    #    the caller sees the original {code, message, status}.
    envelope = getattr(exc, "envelope", None)
    if isinstance(envelope, dict):
        return ToolResult(success=False, error=envelope)

    # 2–4. team_pulse_lib typed exception hierarchy (specific → general)
    if isinstance(exc, TeamPulseAPIError):
        return ToolResult(
            success=False,
            error={
                "code": "api_error",
                "message": str(exc),
                "status": getattr(exc, "status", 0),
            },
        )
    if isinstance(exc, TeamPulseConnectionError):
        return ToolResult(
            success=False,
            error={"code": "transport_error", "message": str(exc), "status": 0},
        )
    if isinstance(exc, TeamPulseError):
        return ToolResult(
            success=False,
            error={"code": "team_pulse_error", "message": str(exc), "status": 0},
        )

    # 5. ValueError (including AzTokenError subclass) and everything else.
    #    Subclasses that carry .code / .status (e.g. AzTokenError) propagate
    #    their specific codes; plain ValueError gets the default.
    return ToolResult(
        success=False,
        error={
            "code": getattr(exc, "code", "invalid_argument"),
            "message": str(exc),
            "status": getattr(exc, "status", 400),
        },
    )


# --- Dataclass JSON helper -------------------------------------------------


def _as_jsonable(obj: Any) -> Any:
    """Best-effort convert a dataclass result to a plain dict.

    Guards with ``is_dataclass`` and ``not isinstance(obj, type)`` so that
    dataclass *instances* are converted via ``asdict`` while dataclass
    *classes* and all non-dataclass values are returned unchanged.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return obj


# --- Base tool class -------------------------------------------------------


class _LensTool:
    """Base class for all team-pulse read (and write) tool adapters.

    Subclasses declare :attr:`name`, :attr:`description`, and override
    :attr:`input_schema` and :meth:`_call`.

    The *provider* argument is intentionally duck-typed so that:
    - In production, a :class:`_ClientProvider` is passed and
      ``provider.client()`` is awaited to obtain the cached client.
    - In tests, a ``TeamPulseClient`` instance (or an ``AsyncMock``) can be
      passed directly; :meth:`execute` detects the absence of a ``client``
      callable and uses the object itself as the client.

    The internal attribute is named ``_client`` (not ``_provider``) for
    backward compatibility with tests that inspect the mounted tool's client.
    """

    name: str = ""
    description: str = ""

    def __init__(self, provider: Any) -> None:
        # Stored as _client for compatibility with tests that access tool._client
        self._client = provider

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for the tool's input.  Subclasses should override this.

        Default: closed empty object (no properties, no additional properties).
        """
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        """Perform the actual API call.  Must be overridden by subclasses."""
        raise NotImplementedError(f"{type(self).__name__}._call is not implemented")

    async def execute(self, input: dict[str, Any]) -> "ToolResult":
        """Resolve the client and delegate to :meth:`_call`.

        Resolution:
        1. If ``self._client`` has a callable ``.client`` attribute (i.e. it is
           a :class:`_ClientProvider`), it is awaited to obtain the cached
           :class:`TeamPulseClient`.  Errors during resolution
           (``TeamPulseError`` or ``ValueError``) surface as the
           ``not_configured`` envelope.
        2. Otherwise ``self._client`` is used directly as the client (enables
           passing a ``TeamPulseClient`` or ``AsyncMock`` in tests).

        Any exception from :meth:`_call` is translated via :func:`_error_result`.
        """
        try:
            client_fn = getattr(self._client, "client", None)
            if callable(client_fn):
                client = await client_fn()  # type: ignore[misc]
            else:
                client = self._client
        except (TeamPulseError, ValueError):
            return ToolResult(success=False, error=_NOT_CONFIGURED_ERROR)

        try:
            return await self._call(client, input)
        except Exception as exc:  # noqa: BLE001
            return _error_result(exc)


# --- Read tool subclasses -------------------------------------------------


class TeamPulseInfoTool(_LensTool):
    """Fetch the team-pulse lens API self-description: name, version,
    available resource_types, capabilities, and endpoint catalog.
    Use this first when you don't yet know what the API exposes."""

    name = "team_pulse_info"
    description = (
        "Describe the SERVER (remote; requires network + working auth). Fetches the "
        "team-pulse lens API's own self-description: API name/version, the auth scheme "
        "the server documents, capabilities, the endpoint catalog, and content "
        "collections. Use to discover what the API exposes. NOTE: this is the server's "
        "view of itself - it does NOT report which URL you are pointed at or how you "
        "authenticated; for your client's resolved config use team_pulse_status."
    )

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.info()
        return ToolResult(success=True, output=output)


class TeamPulseResourcesTool(_LensTool):
    """List team-pulse resources. Returns the list envelope
    {resources: [{id, title, type}], count}. Filter by type to narrow to one
    resource class. Valid types are server-defined and can vary by deployment
    (some entity types have been retired server-side) -- call team_pulse_info()
    and check resource_types for the current live set before assuming a type
    exists."""

    name = "team_pulse_resources"
    description = (
        "List team-pulse resources. Returns the list envelope "
        "{resources: [{id, title, type}], count}. "
        "Filter by type to narrow to one resource class. Valid types are "
        "server-defined and can vary by deployment -- call team_pulse_info() "
        "and check resource_types for the current live set before assuming a "
        "type exists (an unsupported type returns HTTP 400). "
        "For type=question, pass status (active | archived | all) to select lifecycle "
        "state; the default is active (archived questions are hidden unless you ask). "
        "Pass collection to list resources from a content collection folder."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": (
                        "Optional resource type filter. Valid values are "
                        "server-specific -- check team_pulse_info()'s resource_types "
                        "before assuming a type exists."
                    ),
                },
                "collection": {
                    "type": "string",
                    "description": "Optional content collection name, e.g. 'docs'.",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "archived", "all"],
                    "default": "active",
                    "description": (
                        "Lifecycle filter; applies ONLY to type=question (silently "
                        "ignored for other types). 'active' (default) hides archived "
                        "questions; 'archived' returns only archived; 'all' returns "
                        "both. Invalid values -> 400."
                    ),
                },
            },
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.resources(
            type=input.get("type"),
            collection=input.get("collection"),
            status=input.get("status"),
        )
        return ToolResult(success=True, output=output)


class TeamPulseSearchTool(_LensTool):
    """Naive text search across all team-pulse resources. Returns the same list
    envelope as team_pulse_resources. Default limit 50, max 200."""

    name = "team_pulse_search"
    description = (
        "Naive text search across all team-pulse resources. "
        "Returns the same list envelope as team_pulse_resources. "
        "Default limit 50, max 200. "
        "Search is substring-matchy — for precise lookups by ID prefer "
        "team_pulse_get or team_pulse_prefix."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search query string.",
                    "minLength": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (1–200, default 50).",
                    "minimum": 1,
                    "maximum": 200,
                },
                "collection": {
                    "type": "string",
                    "description": "Optional content collection name, e.g. 'docs'.",
                },
            },
            "required": ["q"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.search(
            q=input["q"],
            limit=input.get("limit", 50),
            collection=input.get("collection"),
        )
        return ToolResult(success=True, output=output)


class TeamPulsePrefixTool(_LensTool):
    """List resources whose ID starts with the given path prefix. Example:
    prefix='projects' returns all projects. Cheaper and more precise than
    team_pulse_search for hierarchical lookups."""

    name = "team_pulse_prefix"
    description = (
        "List resources whose ID starts with the given path prefix. "
        "Example: prefix='projects' returns all projects. "
        "Cheaper and more precise than team_pulse_search for hierarchical lookups."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "ID prefix, e.g. 'projects' or 'members'.",
                },
            },
            "required": ["prefix"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.prefix(input["prefix"])
        return ToolResult(success=True, output=output)


class TeamPulseDownloadCorpusTool(_LensTool):
    """Bulk-download the whole mined corpus to a local directory for offline
    use. Fetches the corpus zip in one call, extracts it under dest_dir, and
    returns a SUMMARY (counts, dest_dir, folder) — never the page bodies."""

    name = "team_pulse_download_corpus"
    description = (
        "Bulk-download the whole mined corpus (all sub-corpora the server "
        "exposes) to a LOCAL DIRECTORY, for running your own agents / "
        "embeddings / grep over it offline. Fetches the corpus as a zip in one "
        "call and extracts the .md tree under dest_dir. Returns a SUMMARY "
        "{written, dest_dir, folder, bytes} — NOT the page bodies (pulling "
        "hundreds of docs into context would crash the session). This is the "
        "offline BULK path; for in-session Q&A use team_pulse_search / "
        "team_pulse_get instead. Requires per-user BEARER (az) auth — a shared "
        "API key is refused (403), because a bulk pull must be attributable to "
        "a member. Optionally pass folder to narrow to ONE sub-corpus; the "
        "sub-corpus names are instance-specific — discover them from "
        "team_pulse_info() (collections[].sub_corpora), never assume them."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dest_dir": {
                    "type": "string",
                    "description": ("Local directory to extract the corpus into (created if absent)."),
                },
                "folder": {
                    "type": "string",
                    "description": (
                        "Optional sub-corpus narrow — a sub-corpus id-prefix. "
                        "Names vary per instance; get them from team_pulse_info() "
                        "(collections[].sub_corpora). Omit for the whole corpus. "
                        "An unknown name simply yields an empty result."
                    ),
                },
            },
            "required": ["dest_dir"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        folder = input.get("folder")
        output = await client.download_corpus(dest_dir=input["dest_dir"], folder=folder)
        # Self-correction hint: a 0-file result with a folder narrow almost always
        # means the sub-corpus name was wrong (they are instance-specific). Point
        # the caller at discovery instead of leaving a bare written=0 to puzzle over.
        if isinstance(output, dict) and output.get("written") == 0:
            if folder:
                output["note"] = (
                    f"0 files matched folder {folder!r}. Sub-corpus names are "
                    "instance-specific — list the valid ones with team_pulse_info() "
                    "(collections[].sub_corpora), then retry."
                )
            else:
                output["note"] = "0 files — the corpus is empty or not yet populated on this instance."
        return ToolResult(success=True, output=output)


class TeamPulseGetTool(_LensTool):
    """Fetch a single resource by full ID. Returns the resource envelope
    {id, title, type, data, metadata}. ID shape is '<type>/<slug>', e.g.
    'members/jdoe' or 'questions/higher-level-work'. Available types are
    server-defined -- see team_pulse_info()'s resource_types."""

    name = "team_pulse_get"
    description = (
        "Fetch a single resource by full ID. "
        "Returns the resource envelope {id, title, type, data, metadata}. "
        "ID shape is '<type>/<slug>', e.g. 'members/jdoe' or "
        "'questions/higher-level-work'. Available types are server-defined -- "
        "see team_pulse_info()'s resource_types. "
        "Returns a 404 envelope if unknown."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Full resource ID (e.g. 'projects/team-pulse').",
                },
            },
            "required": ["id"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.get(input["id"])
        return ToolResult(success=True, output=output)


class TeamPulseGraphTool(_LensTool):
    """Fetch the full composed entity graph — every resource of every type plus
    computed reverse edges, in one response. Large payload: prefer
    team_pulse_resources / team_pulse_get for targeted lookups."""

    name = "team_pulse_graph"
    description = (
        "Fetch the full composed entity graph — every resource of every type plus "
        "computed reverse edges, in one response. "
        "Large payload: prefer team_pulse_resources / team_pulse_get for targeted lookups. "
        "Use this when you need cross-resource relationships (who's on what, which projects "
        "roll up to which initiative, etc.)."
    )

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.graph()
        return ToolResult(success=True, output=output)


class TeamPulseWhoamiTool(_LensTool):
    """Resolve the current caller's identity, for requests phrased as
    'me' / 'my' / 'mine'. Returns how the caller authenticated and whether a
    per-user identity is available. This is the SERVER-verified team-pulse
    identity (handle/member_id) -- distinct from team_pulse_status()'s
    az_identity_hint, which is only the raw, unverified Azure token claim and
    may not match this."""

    name = "team_pulse_whoami"
    description = (
        "Resolve the current caller's identity, for requests phrased as "
        "'me' / 'my' / 'mine' (e.g. 'my projects', 'my record', 'what am I assigned'). "
        "Takes no input. Returns how the caller authenticated and whether a per-user "
        "identity is available -- this is the SERVER-verified team-pulse identity "
        "(handle/member_id), distinct from team_pulse_status()'s az_identity_hint "
        "(the raw, unverified Azure token claim, which may not match)."
    )

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.whoami()
        return ToolResult(success=True, output=output)


class TeamPulseAskTool(_LensTool):
    """`ask` is server-side ONLINE GENERATION: a Team Pulse LLM composes a
    bounded answer over current team data. PREFER THE READ TOOLS BY DEFAULT
    (team_pulse_info / team_pulse_search / team_pulse_get / team_pulse_resources):
    answer Team Pulse questions by reading the corpus and composing the response
    yourself — they are cheaper and return full-fidelity data.
    Call team_pulse_ask ONLY when the user explicitly directs Team Pulse to
    answer."""

    name = "team_pulse_ask"
    description = (
        "`ask` is server-side ONLINE GENERATION: a Team Pulse LLM composes a "
        "bounded answer over current team data. "
        "PREFER THE READ TOOLS BY DEFAULT "
        "(team_pulse_info / team_pulse_search / team_pulse_get / team_pulse_resources): "
        "answer Team Pulse questions by reading the corpus and composing the response "
        "yourself — they are cheaper, return full-fidelity data, and you are already "
        "an LLM that can synthesize from raw reads. "
        "Call team_pulse_ask ONLY when the user explicitly directs Team Pulse to answer."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The question to ask Team Pulse.",
                    "minLength": 1,
                },
                "focus": {
                    "type": "string",
                    "description": ("Optional lens resource id for orientation (e.g. 'projects/team-pulse')."),
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        output = await client.ask(
            prompt=input["prompt"],
            focus=input.get("focus"),
        )
        return ToolResult(success=True, output=output)


class TeamPulseSubmitAnswerTool(_LensTool):
    """Submit a session-mined answer to a team-pulse reflection question.
    Use this to record an AI-generated answer attributed to a specific user,
    synthesized from their Context Intelligence sessions.

    question_id is the BARE SLUG (e.g. 'higher-level-work'), NOT the
    hierarchical 'questions/<slug>' form — strip the 'questions/' prefix if
    you have it. Discover valid slugs via team_pulse_resources(type='question')
    and use the data.id field (or strip the prefix from the list-envelope id).

    user_id is the github username of the person the answer is about; the
    bundle records it as a github-namespaced identity (the API stores it
    verbatim and resolves to a team member at read time). metadata is an
    optional opaque bag — session provenance (source_session_ids), timing,
    and any other context live INSIDE it. generated_at is the ISO-8601
    timestamp when the answer was generated."""

    name = "team_pulse_submit_answer"
    description = (
        "Submit a session-mined answer to a team-pulse reflection question. "
        "Use this to record an AI-generated answer attributed to a specific user, "
        "synthesized from their Context Intelligence sessions.\n\n"
        "question_id is the BARE SLUG (e.g. 'higher-level-work'), NOT the "
        "hierarchical 'questions/<slug>' form — strip the 'questions/' prefix if "
        "you have it. Discover valid slugs via team_pulse_resources(type='question') "
        "and use the data.id field (or strip the prefix from the list-envelope id).\n\n"
        "user_id is the github username of the person the answer is about; the "
        "bundle records it as a github-namespaced identity (the API stores it "
        "verbatim and resolves to a team member at read time). "
        "metadata is an optional opaque bag — session provenance "
        "(source_session_ids), timing, and any other context live INSIDE it. "
        "generated_at is the ISO-8601 timestamp when the answer was generated."
    )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9-]*$",
                    "description": (
                        "Bare question slug (e.g. 'higher-level-work'). Hierarchical 'questions/<slug>' is rejected."
                    ),
                },
                "user_id": {
                    "type": "string",
                    "description": "GitHub username of the person the answer is about.",
                },
                "answer": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The answer body.",
                },
                "generated_at": {
                    "type": "string",
                    "description": "ISO-8601 timestamp when the answer was generated.",
                },
                "metadata": {
                    "type": "object",
                    "description": (
                        "Optional opaque bag stored verbatim by the server. Session "
                        "provenance lives here as source_session_ids (array of "
                        "Context Intelligence session IDs); may also carry timing, "
                        "model, confidence, etc."
                    ),
                },
            },
            "required": ["question_id", "user_id", "answer", "generated_at"],
            "additionalProperties": False,
        }

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        upload = AnswerUpload(
            question_id=input["question_id"],
            user_id=input["user_id"],
            answer=input["answer"],
            generated_at=input["generated_at"],
            metadata=input.get("metadata") or {},
        )
        result = await client.upload_answer(upload)
        return ToolResult(success=True, output=_as_jsonable(result))


class TeamPulseStatusTool(_LensTool):
    """Return provenance-only client configuration — never any secret.

    Lists: base_url, auth_mode ('key' | 'az'), api_app_id, credential_type,
    forced, resolved, az_identity_hint (RAW Azure AD token claim, e.g. upn --
    unverified, display-only, None in key mode). az_identity_hint is NOT
    team-pulse's resolved identity and may not match it -- call
    team_pulse_whoami() for the server-verified team member record
    (handle/member_id). The response is built from an explicit field
    allow-list so that a future ClientInfo field that happens to carry a
    secret (key, token, etc.) cannot leak through a blanket spread.
    """

    name = "team_pulse_status"
    description = (
        "Report THIS client's locally-resolved config (no network call, no secrets). "
        "Lists: base_url (the team-pulse endpoint you are pointed at), "
        "auth_mode ('key' | 'az'), credential_type, api_app_id, forced, resolved, "
        "az_identity_hint (the raw Azure AD token's own claim -- e.g. upn -- decoded "
        "client-side, signature NOT verified, None in key mode). "
        "az_identity_hint is NOT team-pulse's resolved identity and may not match "
        "it -- for the server-verified team member record (handle/member_id), use "
        "team_pulse_whoami instead. "
        "Answers 'which server am I talking to and how am I authenticating?' and "
        "works even when auth is broken or the server is unreachable — use it to "
        "diagnose auth/connection failures. For the SERVER's own documented "
        "capabilities and endpoints, use team_pulse_info instead."
    )

    # input_schema inherits the closed empty object from _LensTool:
    # {type: object, properties: {}, additionalProperties: False}

    async def _call(self, client: Any, input: dict[str, Any]) -> "ToolResult":
        info = await client.describe()
        # Explicit allow-list — never spread info.__dict__ or asdict(info).
        # This ensures no future secret field (key, token, etc.) can leak.
        return ToolResult(
            success=True,
            output={
                "base_url": info.base_url,
                "auth_mode": info.auth_mode,
                "api_app_id": info.api_app_id,
                "credential_type": info.credential_type,
                "forced": info.forced,
                "resolved": info.resolved,
                "az_identity_hint": info.az_identity_hint,
            },
        )


# --- Configure tool -------------------------------------------------------


class TeamPulseConfigureTool:
    """Persist the team-pulse endpoint URL (and optional client_id) to disk.

    Always mounted, even when team-pulse is otherwise unconfigured.  After a
    successful save it resets the shared provider so the next data-tool call
    rebuilds the client from the freshly-saved config — live in the same
    session, no restart.

    This bundle prefers Azure AD (bearer) auth: this tool only ever sets the
    URL (+ optional az app id) -- it has no ``key`` parameter and never will,
    by design. “Already az login'd” + this tool's URL save is the complete
    setup. A shared API key exists for automation/service scenarios where
    bearer genuinely isn't viable, but it is configured OUTSIDE this tool
    (env var or a manual settings.yaml/config.yaml edit) -- deliberately not
    a first-class option here, so the interactive path always steers toward
    az.
    """

    name = "team_pulse_configure"
    description = (
        "Set and persist the team-pulse endpoint URL for this user. Saved to "
        "~/.amplifier/team-pulse/config.yaml (or $AMPLIFIER_TEAM_PULSE_DIR/config.yaml). "
        "Call this when the user provides their team-pulse endpoint URL, then the data "
        "tools become available immediately — no restart needed. "
        "(client_id is optional — only set it to override the built-in default.) "
        "This bundle prefers Azure AD (bearer) auth -- if you're already az "
        "login'd, setting the URL here is the entire setup, no key needed. "
        "This tool has no key parameter by design; a shared API key (for "
        "automation/service scenarios where bearer isn't viable) is set via "
        "AMPLIFIER_TEAM_PULSE_KEY instead, and takes precedence over az when "
        "both are present -- only set one if you specifically need it."
    )

    def __init__(self, provider: "_ClientProvider") -> None:
        self._provider = provider

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Team-pulse endpoint URL (must start with https://).",
                },
                "client_id": {
                    "type": "string",
                    "description": (
                        "Azure AD application (client) ID (optional; used for az auth mode). "
                        "Omit to use the built-in default."
                    ),
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        }

    async def execute(self, input: dict[str, Any]) -> "ToolResult":
        url = (input.get("url") or "").strip()
        if not url or not url.startswith("https://"):
            return ToolResult(
                success=False,
                error={"code": "invalid_url", "message": "url must be a non-empty https:// URL"},
            )

        client_id = (input.get("client_id") or "").strip()

        # Thin caller: the atomic-write/merge/persist logic lives in the library
        # (team_pulse_lib.config.save_config).  The shim carries NONE of it.
        # Exact 0A signature: save_config(url, api_app_id=None, *, path=None) -> Path.
        # client_id is the legacy alias for api_app_id; pass None when absent so
        # the lib preserves any existing app-id key on disk.
        path = tpl_config.save_config(url, api_app_id=client_id or None)

        # Reset the shared provider so the next tool call rebuilds with new config.
        await self._provider.reset()

        output: dict[str, Any] = {
            "saved_url": url,
            "persisted_path": str(path),
            "message": (f"Saved to {path}. team-pulse is now configured and live in this session — no restart needed."),
        }
        if client_id:
            output["saved_client_id"] = client_id

        # Advisory only, changes no behavior: a key present anywhere in the
        # resolution chain wins over az (key-wins auth inference in
        # team_pulse_lib's config.py), which can silently override the az/bearer
        # setup this tool just persisted. Surface that rather than leave it a
        # silent surprise -- this tool has no key parameter, so the only way a
        # key got here is an env var (or a settings.yaml override bridged to one).
        if os.environ.get("AMPLIFIER_TEAM_PULSE_KEY", "").strip():
            output["note"] = (
                "AMPLIFIER_TEAM_PULSE_KEY is set in this environment and will take "
                "precedence over az/bearer (key-wins auth inference). Unset it if "
                "you want this az configuration to actually be used."
            )

        return ToolResult(success=True, output=output)


# --- Provider-backed mount() ---------------------------------------------------
#
# Task 6: rewrite mount() to be provider-backed with no resolution logic.
# Config resolution is delegated to team_pulse_lib via an env bridge (_make_build).
# No inline config-validation helpers or hardcoded defaults — lib owns all of that.
#
# Public identifiers added here:
#   _DATA_TOOL_CLASSES  — ordered list of data tool classes (excludes configure)
#   _SETTINGS_TO_ENV    — (settings_key, env_var) mapping for config bridging
#   _make_build(config) — factory that returns the lazy async _build coroutine
#   mount(coordinator, config=None) — Amplifier entry point

#: Ordered list of data tool classes mounted after TeamPulseConfigureTool.
#: Does NOT include TeamPulseConfigureTool (always mounted first, separately).
_DATA_TOOL_CLASSES: list[type[_LensTool]] = [
    TeamPulseInfoTool,
    TeamPulseWhoamiTool,
    TeamPulseResourcesTool,
    TeamPulseSearchTool,
    TeamPulsePrefixTool,
    TeamPulseGetTool,
    TeamPulseGraphTool,
    TeamPulseDownloadCorpusTool,
    TeamPulseSubmitAnswerTool,
    TeamPulseAskTool,
    TeamPulseStatusTool,
]

#: Alias kept for backward compatibility with tests; mount() uses _DATA_TOOL_CLASSES.
_TOOL_CLASSES = _DATA_TOOL_CLASSES

#: Ordered mapping of (settings_key, env_var) pairs used by _make_build.
#: client_id is an alias for api_app_id — both target AMPLIFIER_TEAM_PULSE_API_APP_ID.
#: When both are present in config, the later entry (client_id) wins.
_SETTINGS_TO_ENV: list[tuple[str, str]] = [
    ("url", "AMPLIFIER_TEAM_PULSE_URL"),
    ("key", "AMPLIFIER_TEAM_PULSE_KEY"),
    ("api_app_id", "AMPLIFIER_TEAM_PULSE_API_APP_ID"),
    ("client_id", "AMPLIFIER_TEAM_PULSE_API_APP_ID"),  # alias — overwrites api_app_id
    ("auth_mode", "AMPLIFIER_TEAM_PULSE_AUTH_MODE"),
]


def _make_build(config: dict[str, Any]) -> "Callable[[], Awaitable[TeamPulseClient]]":
    """Return an async _build coroutine that bridges config into env, then calls from_env.

    For each (settings_key, env_name) in _SETTINGS_TO_ENV, if the stripped value
    at config[settings_key] is non-empty, os.environ[env_name] is set to that value.
    Settings-present wins over any pre-existing env value (mechanical glue, ZERO inference).

    TeamPulseClient.from_env() is then called with no overrides — the lib owns all
    precedence/key-wins inference/auth_mode migration.  Missing URL surfaces as
    not_configured at call time (via the _LensTool.execute() exception handler),
    never at mount() time.
    """

    async def _build() -> TeamPulseClient:
        for settings_key, env_name in _SETTINGS_TO_ENV:
            value = (config.get(settings_key) or "").strip()
            if value:
                os.environ[env_name] = value
        return TeamPulseClient.from_env()

    return _build


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount team-pulse tools onto the Amplifier coordinator.

    Builds a single shared :class:`_ClientProvider` whose lazy ``_build``
    bridges settings into env and then calls ``TeamPulseClient.from_env()``.

    Mount order:
      1. :class:`TeamPulseConfigureTool` — always first.
      2. All classes in :data:`_DATA_TOOL_CLASSES` — in listed order.

    A missing URL is NOT an error at mount time.  It surfaces as a
    ``not_configured`` :class:`ToolResult` at the first call to any data tool,
    prompting the agent to call ``team_pulse_configure``.

    Args:
        coordinator: Amplifier coordinator; must have an async
            ``mount(kind, tool, name=...)`` method.
        config: Behavior/settings dict (may be ``None`` or empty).
    """
    config = config or {}
    provider = _ClientProvider(build=_make_build(config))

    # Configure tool is always first — always mounted, even when unconfigured.
    configure_tool = TeamPulseConfigureTool(provider)
    await coordinator.mount("tools", configure_tool, name=configure_tool.name)

    # Mount all data tools sharing the same provider.
    for cls in _DATA_TOOL_CLASSES:
        tool = cls(provider)
        await coordinator.mount("tools", tool, name=tool.name)

    logger.info("team-pulse: mounted %d tools", 1 + len(_DATA_TOOL_CLASSES))
