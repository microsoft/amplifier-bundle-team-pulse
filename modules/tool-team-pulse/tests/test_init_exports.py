# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for __init__.py public surface after shim deletion (Task 7).

Acceptance criteria:
- __all__ lists exactly the 13 tool classes + 'mount' (14 names total).
- Legacy shim symbols are NOT exported (ApiKeyAuth, AzTokenAuth, AzTokenError,
  TeamPulseAPIError, TeamPulseClient, _ClientProvider, ToolResult).
- __amplifier_module_type__ == 'tool'.
- sorted(__all__) produces the expected 14-name list ending with 'mount'.
"""


def test_all_contains_exactly_the_tool_classes_and_mount():
    """__all__ must list exactly the 13 public tool classes plus 'mount'."""
    import amplifier_module_tool_team_pulse as m

    expected = sorted(
        [
            "TeamPulseAskTool",
            "TeamPulseConfigureTool",
            "TeamPulseDownloadAnswersTool",
            "TeamPulseDownloadCorpusTool",
            "TeamPulseGetTool",
            "TeamPulseGraphTool",
            "TeamPulseInfoTool",
            "TeamPulsePrefixTool",
            "TeamPulseResourcesTool",
            "TeamPulseSearchTool",
            "TeamPulseStatusTool",
            "TeamPulseSubmitAnswerTool",
            "TeamPulseWhoamiTool",
            "mount",
        ]
    )
    assert sorted(m.__all__) == expected


def test_all_has_exactly_14_names():
    """__all__ must have exactly 14 names (13 tools + mount)."""
    import amplifier_module_tool_team_pulse as m

    assert len(m.__all__) == 14


def test_legacy_shim_symbols_not_in_all():
    """Legacy shim symbols from client.py must NOT appear in __all__."""
    import amplifier_module_tool_team_pulse as m

    legacy = [
        "ApiKeyAuth",
        "AzTokenAuth",
        "AzTokenError",
        "TeamPulseAPIError",
        "TeamPulseClient",
        "_ClientProvider",
        "ToolResult",
    ]
    for name in legacy:
        assert name not in m.__all__, f"{name!r} should not be in __all__"


def test_amplifier_module_type_is_tool():
    """__amplifier_module_type__ must be 'tool'."""
    import amplifier_module_tool_team_pulse as m

    assert m.__amplifier_module_type__ == "tool"


def test_all_tool_classes_are_importable():
    """All 12 tool classes must be importable from the package."""
    from amplifier_module_tool_team_pulse import (
        TeamPulseAskTool,
        TeamPulseConfigureTool,
        TeamPulseDownloadAnswersTool,
        TeamPulseDownloadCorpusTool,
        TeamPulseGetTool,
        TeamPulseGraphTool,
        TeamPulseInfoTool,
        TeamPulsePrefixTool,
        TeamPulseResourcesTool,
        TeamPulseSearchTool,
        TeamPulseStatusTool,
        TeamPulseSubmitAnswerTool,
        TeamPulseWhoamiTool,
        mount,
    )

    # All are non-None
    for cls in [
        TeamPulseAskTool,
        TeamPulseConfigureTool,
        TeamPulseDownloadAnswersTool,
        TeamPulseDownloadCorpusTool,
        TeamPulseGetTool,
        TeamPulseGraphTool,
        TeamPulseInfoTool,
        TeamPulsePrefixTool,
        TeamPulseResourcesTool,
        TeamPulseSearchTool,
        TeamPulseStatusTool,
        TeamPulseSubmitAnswerTool,
        TeamPulseWhoamiTool,
    ]:
        assert cls is not None
    assert mount is not None


def test_team_pulse_status_tool_in_all():
    """TeamPulseStatusTool specifically must be in __all__ (explicit acceptance criterion)."""
    import amplifier_module_tool_team_pulse as m

    assert "TeamPulseStatusTool" in m.__all__
