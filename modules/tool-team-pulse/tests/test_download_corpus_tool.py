# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for TeamPulseDownloadCorpusTool (the bulk offline-pull tool).

The tool forwards dest_dir + folder to client.download_corpus and returns the
summary verbatim — it never returns page bodies. It is registered in the data
tool list and exported from the package.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from amplifier_module_tool_team_pulse import TeamPulseDownloadCorpusTool
from amplifier_module_tool_team_pulse.tool import (
    _DATA_TOOL_CLASSES,
)
from amplifier_module_tool_team_pulse.tool import (
    TeamPulseDownloadCorpusTool as _ToolFromModule,
)


def _make_provider(mock_client: AsyncMock) -> MagicMock:
    provider = MagicMock()
    provider.client = AsyncMock(return_value=mock_client)
    return provider


async def test_forwards_dest_dir_and_folder_and_returns_summary() -> None:
    summary = {
        "written": 1421,
        "dest_dir": "/tmp/corpus",
        "folder": "repos",
        "bytes": 4_300_000,
    }
    mock_client = AsyncMock()
    mock_client.download_corpus.return_value = summary

    tool = TeamPulseDownloadCorpusTool(_make_provider(mock_client))
    result = await tool.execute({"dest_dir": "/tmp/corpus", "folder": "repos"})

    assert result.success is True
    assert result.output == summary
    mock_client.download_corpus.assert_awaited_once_with(dest_dir="/tmp/corpus", folder="repos")


async def test_folder_optional() -> None:
    mock_client = AsyncMock()
    mock_client.download_corpus.return_value = {"written": 0}
    tool = TeamPulseDownloadCorpusTool(_make_provider(mock_client))

    await tool.execute({"dest_dir": "/tmp/corpus"})

    mock_client.download_corpus.assert_awaited_once_with(dest_dir="/tmp/corpus", folder=None)


def test_tool_metadata_and_schema() -> None:
    tool = TeamPulseDownloadCorpusTool(MagicMock())
    assert tool.name == "team_pulse_download_corpus"
    schema = tool.input_schema
    assert schema["required"] == ["dest_dir"]
    folder = schema["properties"]["folder"]
    assert folder["type"] == "string"
    # Data-agnostic: sub-corpus names are instance-specific and discovered via
    # team_pulse_info, so the schema must NOT hard-code a made-team enum.
    assert "enum" not in folder
    assert "sub_corpora" in folder["description"]
    assert schema["additionalProperties"] is False


def test_registered_in_data_tool_classes() -> None:
    assert _ToolFromModule in _DATA_TOOL_CLASSES


async def test_written_zero_with_folder_adds_discovery_note() -> None:
    """A 0-file result for a folder narrow gets a self-correction hint so the
    model can discover the real sub-corpus names instead of puzzling over it."""
    mock_client = AsyncMock()
    mock_client.download_corpus.return_value = {
        "written": 0,
        "dest_dir": "/tmp/corpus",
        "folder": "code",
        "bytes": 22,
    }
    tool = TeamPulseDownloadCorpusTool(_make_provider(mock_client))
    result = await tool.execute({"dest_dir": "/tmp/corpus", "folder": "code"})

    assert result.success is True
    assert "note" in result.output
    assert "team_pulse_info" in result.output["note"]
    assert "code" in result.output["note"]


async def test_written_nonzero_has_no_note() -> None:
    """A normal (non-empty) result is returned verbatim — no note noise."""
    mock_client = AsyncMock()
    mock_client.download_corpus.return_value = {
        "written": 1542,
        "dest_dir": "/tmp/corpus",
        "folder": None,
        "bytes": 4437660,
    }
    tool = TeamPulseDownloadCorpusTool(_make_provider(mock_client))
    result = await tool.execute({"dest_dir": "/tmp/corpus"})

    assert result.success is True
    assert "note" not in result.output
