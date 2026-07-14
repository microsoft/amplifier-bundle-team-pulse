# SPDX-License-Identifier: MIT
"""Tests for TeamPulseClient.download_corpus (bulk zip -> disk).

The client fetches GET /api/lens/corpus/download (Door 2, bearer-only on the
server), extracts the zip tree under dest_dir, and returns a provenance summary
(never the page bodies). Zip-slip members are refused.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import respx

from team_pulse_lib.client import TeamPulseClient, _extract_zip_safely

BASE_URL = "https://team-pulse.test"


class FakeAuth:
    """Minimal AuthStrategy stub — injects a bearer header."""

    async def headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer fake.token"}


def _zip(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, body in members.items():
            z.writestr(name, body)
    return buf.getvalue()


_CORPUS = {
    "corpus/conversations/alpha.md": "# Alpha\n",
    "corpus/conversations/beta.md": "# Beta\n",
    "corpus/repos/gamma.md": "# Gamma\n",
    "corpus/repos/_sources/src1.md": "# Source\n",
}


@respx.mock
async def test_download_corpus_extracts_tree_and_returns_summary(tmp_path: Path) -> None:
    zip_bytes = _zip(_CORPUS)
    route = respx.get(f"{BASE_URL}/api/lens/corpus/download").mock(return_value=httpx.Response(200, content=zip_bytes))
    dest = tmp_path / "corpus-dump"

    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        summary = await client.download_corpus(dest_dir=dest)

    assert route.called
    assert summary["written"] == 4
    assert summary["folder"] is None
    assert summary["bytes"] == len(zip_bytes)
    assert Path(summary["dest_dir"]) == dest
    # Files actually landed on disk with content preserved.
    assert (dest / "corpus/conversations/alpha.md").read_text() == "# Alpha\n"
    assert (dest / "corpus/repos/_sources/src1.md").read_text() == "# Source\n"


@respx.mock
async def test_download_corpus_forwards_folder_param(tmp_path: Path) -> None:
    route = respx.get(f"{BASE_URL}/api/lens/corpus/download").mock(
        return_value=httpx.Response(200, content=_zip({"corpus/repos/gamma.md": "x\n"}))
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        summary = await client.download_corpus(dest_dir=tmp_path, folder="repos")

    assert route.called
    assert route.calls[0].request.url.params["folder"] == "repos"
    assert summary["folder"] == "repos"


@respx.mock
async def test_download_corpus_403_raises_auth_error(tmp_path: Path) -> None:
    from team_pulse_lib.errors import TeamPulseAuthError

    respx.get(f"{BASE_URL}/api/lens/corpus/download").mock(
        return_value=httpx.Response(403, json={"error": {"code": "bearer_required", "message": "x", "status": 403}})
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        try:
            await client.download_corpus(dest_dir=tmp_path)
        except TeamPulseAuthError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected TeamPulseAuthError for 403")


@respx.mock
async def test_auth_error_surfaces_server_message(tmp_path: Path) -> None:
    """The client must preserve the server's actionable auth message (e.g. the
    bearer_required explanation) so an agent can self-correct — not swallow it
    behind the generic client-side hint."""
    from team_pulse_lib.errors import TeamPulseAuthError

    server_msg = (
        "Corpus download requires bearer (Entra) authentication; a shared API "
        "key cannot attribute a bulk pull to a specific member."
    )
    respx.get(f"{BASE_URL}/api/lens/corpus/download").mock(
        return_value=httpx.Response(
            403, json={"error": {"code": "bearer_required", "message": server_msg, "status": 403}}
        )
    )
    async with TeamPulseClient(base_url=BASE_URL, auth=FakeAuth()) as client:
        try:
            await client.download_corpus(dest_dir=tmp_path)
        except TeamPulseAuthError as exc:
            assert "Server said:" in str(exc)
            assert "shared API key cannot attribute a bulk pull" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected TeamPulseAuthError for 403")


def test_extract_zip_safely_refuses_zip_slip(tmp_path: Path) -> None:
    # A malicious member trying to escape dest must be skipped, not written.
    evil = _zip({"../escape.md": "pwned\n", "corpus/ok.md": "fine\n"})
    written = _extract_zip_safely(evil, tmp_path / "out")
    assert written == 1
    assert (tmp_path / "out" / "corpus" / "ok.md").is_file()
    assert not (tmp_path / "escape.md").exists()
