# SPDX-License-Identifier: MIT
"""Stdlib-only fake Team Pulse server for running examples end-to-end.

No external dependencies beyond the Python standard library.  Uses
``http.server.ThreadingHTTPServer`` in a daemon background thread so example
scripts and tests can make **real** HTTP calls against a genuine localhost
socket — no mocking inside the examples themselves.

Implements the exact subset of the Team Pulse lens API that the examples need:

* ``GET  /api/lens/info``                        — capability/info payload
* ``GET  /api/lens/resources?type=question``     — list of question stubs
* ``GET  /api/lens/resources/questions/{slug}``  — single question
* ``POST /api/lens/answers``                     — accept an answer; 201 on
  first submit, 200 (idempotent) on the same ``question_id`` again

The ``advertise_metadata`` constructor flag toggles which capability posture
the server advertises:

* ``False`` (default) — no ``capabilities`` key in the info payload.
* ``True``  — full capabilities dict advertising ``metadata``, ``user_id``,
  and ``lookback_days``.

Usage (context manager — yields the base_url string)::

    with FakeTeamPulseServer(advertise_metadata=False) as base_url:
        # base_url == "http://127.0.0.1:<ephemeral_port>"
        async with TeamPulseClient.connect(base_url=base_url, key="tp_demo") as client:
            ...

Usage (explicit start / stop — lets you inspect submitted_answers)::

    server = FakeTeamPulseServer(advertise_metadata=True)
    base_url = server.start()
    try:
        ...
        assert len(server.submitted_answers) == 1
    finally:
        server.stop()
"""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Fixture question data
# ---------------------------------------------------------------------------

_QUESTIONS: list[dict] = [
    {
        "id": "questions/higher-level-work",
        "type": "question",
        "data": {
            "id": "higher-level-work",
            "question": "What higher-level work did you accomplish this week?",
            "status": "active",
            "lookback_days": 7,
        },
    },
    {
        "id": "questions/effective-practices",
        "type": "question",
        "data": {
            "id": "effective-practices",
            "question": "What engineering practices made your team most effective?",
            "status": "active",
            "lookback_days": 14,
        },
    },
    {
        "id": "questions/team-blockers",
        "type": "question",
        "data": {
            "id": "team-blockers",
            "question": "What blockers did your team encounter this week?",
            "status": "active",
            # lookback_days intentionally absent — client must surface None
        },
    },
    {
        "id": "questions/old-retro",
        "type": "question",
        "data": {
            "id": "old-retro",
            "question": "An archived retrospective question no longer in rotation.",
            "status": "archived",
        },
    },
]

# Pre-index for O(1) single-question lookups.
_QUESTIONS_BY_SLUG: dict[str, dict] = {q["data"]["id"]: q for q in _QUESTIONS}


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the fake Team Pulse lens API."""

    # Suppress per-request log lines; example output stays clean.
    def log_message(self, format, *args):  # noqa: A002
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_json(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # GET /api/lens/info
        if path == "/api/lens/info":
            self._send_json(200, self.server.info_body)  # type: ignore[attr-defined]
            return

        # GET /api/lens/resources[?type=question]
        if path == "/api/lens/resources":
            resource_type = (qs.get("type") or [None])[0]
            resources = _QUESTIONS if resource_type == "question" else []
            self._send_json(200, {"resources": resources, "count": len(resources)})
            return

        # GET /api/lens/resources/questions/{slug}
        if path.startswith("/api/lens/resources/questions/"):
            slug = path[len("/api/lens/resources/questions/") :]
            if slug in _QUESTIONS_BY_SLUG:
                self._send_json(200, _QUESTIONS_BY_SLUG[slug])
            else:
                self._send_json(404, {"error": f"Question not found: {slug}"})
            return

        self._send_json(404, {"error": f"Not found: {path}"})

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        # POST /api/lens/answers
        if path == "/api/lens/answers":
            length = int(self.headers.get("Content-Length", 0))
            body: dict = json.loads(self.rfile.read(length))
            question_id: str = body.get("question_id", "")

            # Idempotency: same question_id submitted twice → 200 with the
            # existing record.  First submit → 201 with a fresh record.
            submitted: list[dict] = self.server.submitted_answers  # type: ignore[attr-defined]
            existing = next((a for a in submitted if a.get("question_id") == question_id), None)
            if existing:
                self._send_json(200, {"id": existing["id"], "question_id": existing["question_id"]})
                return

            record = {"id": f"ans-{uuid.uuid4().hex[:8]}", "question_id": question_id, **body}
            submitted.append(record)
            self._send_json(201, {"id": record["id"], "question_id": record["question_id"]})
            return

        self._send_json(404, {"error": f"Not found: {path}"})


# ---------------------------------------------------------------------------
# FakeTeamPulseServer
# ---------------------------------------------------------------------------


class FakeTeamPulseServer:
    """Self-contained fake Team Pulse HTTP server — stdlib only.

    Binds to an ephemeral ``127.0.0.1`` port, runs in a daemon thread.
    Submitted answers accumulate in-memory and are accessible via
    :attr:`submitted_answers` for post-run assertions.

    Args:
        advertise_metadata: When ``True``, ``GET /api/lens/info`` returns
            ``{"capabilities": {"metadata": True, "user_id": True,
            "lookback_days": True}}``.  When ``False`` (default), the info
            payload has **no** ``capabilities`` key.

    Context-manager form (yields the ``str`` base_url)::

        with FakeTeamPulseServer(advertise_metadata=False) as base_url:
            ...  # base_url = "http://127.0.0.1:<port>"

    Manual form (allows accessing :attr:`submitted_answers`)::

        server = FakeTeamPulseServer()
        base_url = server.start()
        ...
        print(server.submitted_answers)
        server.stop()
    """

    def __init__(self, *, advertise_metadata: bool = False) -> None:
        self._advertise_metadata = advertise_metadata
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        """``http://127.0.0.1:<port>`` for the running server."""
        if self._server is None:
            raise RuntimeError("Server is not started; call start() first.")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    @property
    def submitted_answers(self) -> list[dict]:
        """Live reference to the in-memory submitted-answers list.

        Each entry is the full request body dict plus an ``"id"`` key.
        Inspect this after a run to assert what the client actually sent.
        """
        if self._server is None:
            raise RuntimeError("Server is not started; call start() first.")
        return self._server.submitted_answers  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Info-body factory
    # ------------------------------------------------------------------

    def _info_body(self) -> dict:
        if self._advertise_metadata:
            return {
                "name": "fake-team-pulse",
                "version": "1.0.0-supporting",
                "capabilities": {"metadata": True, "user_id": True, "lookback_days": True},
            }
        return {
            "name": "fake-team-pulse",
            "version": "0.9.0-phase0",
            # No 'capabilities' key in the info payload.
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> str:
        """Bind, start the background thread, and return :attr:`base_url`."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.info_body = self._info_body()  # type: ignore[attr-defined]
        server.submitted_answers = []  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        """Shut down the server and join the daemon thread."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    # ------------------------------------------------------------------
    # Context-manager interface (yields the base_url string)
    # ------------------------------------------------------------------

    def __enter__(self) -> str:
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
