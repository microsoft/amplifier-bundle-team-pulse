# SPDX-License-Identifier: MIT
"""Client contract tests for TeamPulseClient.download_answers.

Asserts the WIRE contract + the footgun guards (not server behavior):
- None -> download all (no `questions` param)
- explicit empty (`[]` / `""` / `","`) -> ValueError, never a wide-open pull
- list -> single CSV `questions` param; tuple -> same CSV (iterable, not just list)
- whitespace/empty-segment hygiene
- `unmatched` computed from the extracted manifest.json (server-normalized diff)
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from team_pulse_lib.auth import ApiKeyAuth
from team_pulse_lib.client import TeamPulseClient


def _zip_bytes(manifest: dict | None = None, extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if manifest is not None:
            z.writestr("manifest.json", json.dumps(manifest))
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def _client_with(handler) -> TeamPulseClient:
    transport = httpx.MockTransport(handler)
    c = TeamPulseClient(base_url="https://tp.example", auth=ApiKeyAuth("tp_x"))
    c._http = httpx.AsyncClient(transport=transport, base_url="https://tp.example")
    return c


async def test_none_downloads_all_no_questions_param(tmp_path: Path) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, content=_zip_bytes({"scope": {"questions": None}, "questions": []}))

    c = _client_with(handler)
    out = await c.download_answers(tmp_path, questions=None)
    assert "questions" not in seen["params"]  # omitted -> all
    assert out["questions"] is None
    assert out["unmatched"] is None


@pytest.mark.parametrize("empty", [[], "", ",", "  ,  ", ()])
async def test_explicit_empty_raises(tmp_path: Path, empty) -> None:
    c = _client_with(lambda r: httpx.Response(200, content=_zip_bytes()))
    with pytest.raises(ValueError, match="empty"):
        await c.download_answers(tmp_path, questions=empty)


async def test_list_becomes_single_csv_param(tmp_path: Path) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # capture raw query so we can prove it's ONE csv param, not repeated
        seen["raw"] = request.url.query.decode()
        return httpx.Response(
            200,
            content=_zip_bytes(
                {"scope": {"questions": ["a", "b"]}, "questions": [{"question_id": "a"}, {"question_id": "b"}]}
            ),
        )

    c = _client_with(handler)
    out = await c.download_answers(tmp_path, questions=["a", "b"])
    assert "questions=a%2Cb" in seen["raw"] or "questions=a,b" in seen["raw"]
    assert out["questions"] == "a,b"


async def test_tuple_same_as_list(tmp_path: Path) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            content=_zip_bytes(
                {"scope": {"questions": ["a", "b"]}, "questions": [{"question_id": "a"}, {"question_id": "b"}]}
            ),
        )

    c = _client_with(handler)
    await c.download_answers(tmp_path, questions=("a", "b"))
    assert seen["params"]["questions"] == "a,b"  # tuple -> CSV, not repeated params


async def test_whitespace_and_empty_segments_stripped(tmp_path: Path) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            content=_zip_bytes(
                {"scope": {"questions": ["a", "b"]}, "questions": [{"question_id": "a"}, {"question_id": "b"}]}
            ),
        )

    c = _client_with(handler)
    await c.download_answers(tmp_path, questions="a, ,b")
    assert seen["params"]["questions"] == "a,b"


async def test_unmatched_from_manifest(tmp_path: Path) -> None:
    manifest = {
        "scope": {"questions": ["a", "typo"]},
        "questions": [{"question_id": "a"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_zip_bytes(manifest, {"qa/a.json": b"{}"}))

    c = _client_with(handler)
    out = await c.download_answers(tmp_path, questions=["a", "typo"])
    assert out["unmatched"] == ["typo"]


async def test_unmatched_none_when_manifest_absent(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_zip_bytes(None, {"qa/a.json": b"{}"}))

    c = _client_with(handler)
    out = await c.download_answers(tmp_path, questions=["a"])
    assert out["unmatched"] is None  # graceful — never fails the download
