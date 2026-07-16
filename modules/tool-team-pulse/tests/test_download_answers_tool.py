# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for TeamPulseDownloadAnswersTool (the bulk offline Q&A-pull tool).

The tool forwards dest_dir + questions (an array) to client.download_answers and
returns the summary verbatim — never answer bodies. It surfaces the client's
`unmatched` as a self-correction note. Registered in the data tool list and
exported from the package.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from amplifier_module_tool_team_pulse import TeamPulseDownloadAnswersTool
from amplifier_module_tool_team_pulse.tool import (
    _DATA_TOOL_CLASSES,
)
from amplifier_module_tool_team_pulse.tool import (
    TeamPulseDownloadAnswersTool as _ToolFromModule,
)


def _make_provider(mock_client: AsyncMock) -> MagicMock:
    provider = MagicMock()
    provider.client = AsyncMock(return_value=mock_client)
    return provider


async def test_forwards_dest_dir_and_questions_and_returns_summary() -> None:
    summary = {
        "written": 8,
        "dest_dir": "/tmp/answers",
        "questions": "higher-level-work",
        "unmatched": [],
        "bytes": 120_000,
    }
    mock_client = AsyncMock()
    mock_client.download_answers.return_value = summary

    tool = TeamPulseDownloadAnswersTool(_make_provider(mock_client))
    result = await tool.execute(
        {"dest_dir": "/tmp/answers", "questions": ["higher-level-work"]}
    )

    assert result.success is True
    assert result.output == summary
    mock_client.download_answers.assert_awaited_once_with(
        dest_dir="/tmp/answers", questions=["higher-level-work"]
    )


async def test_questions_optional_maps_to_none() -> None:
    mock_client = AsyncMock()
    mock_client.download_answers.return_value = {"written": 0, "unmatched": None}
    tool = TeamPulseDownloadAnswersTool(_make_provider(mock_client))

    await tool.execute({"dest_dir": "/tmp/answers"})

    mock_client.download_answers.assert_awaited_once_with(
        dest_dir="/tmp/answers", questions=None
    )


async def test_empty_array_coerced_to_none() -> None:
    """An empty array from the model is coerced to None (= all), never passed as []
    (which the client would reject)."""
    mock_client = AsyncMock()
    mock_client.download_answers.return_value = {"written": 4, "unmatched": None}
    tool = TeamPulseDownloadAnswersTool(_make_provider(mock_client))

    await tool.execute({"dest_dir": "/tmp/answers", "questions": []})

    mock_client.download_answers.assert_awaited_once_with(
        dest_dir="/tmp/answers", questions=None
    )


def test_tool_metadata_and_schema() -> None:
    tool = TeamPulseDownloadAnswersTool(MagicMock())
    assert tool.name == "team_pulse_download_answers"
    schema = tool.input_schema
    assert schema["required"] == ["dest_dir"]
    questions = schema["properties"]["questions"]
    # Array of strings — the LLM-friendly shape for a plural narrow.
    assert questions["type"] == "array"
    assert questions["items"]["type"] == "string"
    assert "team_pulse_resources" in questions["description"]
    assert schema["additionalProperties"] is False


def test_registered_in_data_tool_classes() -> None:
    assert _ToolFromModule in _DATA_TOOL_CLASSES


async def test_unmatched_adds_self_correction_note() -> None:
    """A partial miss (some ids matched nothing) surfaces a note listing them."""
    mock_client = AsyncMock()
    mock_client.download_answers.return_value = {
        "written": 3,
        "dest_dir": "/tmp/answers",
        "questions": "higher-level-work,nope",
        "unmatched": ["nope"],
        "bytes": 60_000,
    }
    tool = TeamPulseDownloadAnswersTool(_make_provider(mock_client))
    result = await tool.execute(
        {"dest_dir": "/tmp/answers", "questions": ["higher-level-work", "nope"]}
    )

    assert result.success is True
    assert "note" in result.output
    assert "nope" in result.output["note"]
    assert "team_pulse_resources" in result.output["note"]


async def test_no_unmatched_no_note() -> None:
    """A clean result (nothing unmatched) is returned verbatim — no note noise."""
    mock_client = AsyncMock()
    mock_client.download_answers.return_value = {
        "written": 8,
        "dest_dir": "/tmp/answers",
        "questions": None,
        "unmatched": None,
        "bytes": 120_000,
    }
    tool = TeamPulseDownloadAnswersTool(_make_provider(mock_client))
    result = await tool.execute({"dest_dir": "/tmp/answers"})

    assert result.success is True
    assert "note" not in result.output
