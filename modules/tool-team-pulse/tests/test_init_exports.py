# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for the __init__.py public surface.

Acceptance criteria:
- __all__ lists exactly the 14 tool classes + COMPAT_TABLE + 'mount'.
  The 14 are the 3 MOUNTED tools (read / write / ask) plus the 11 per-op
  handler classes, which stay importable because they hold the per-op
  request/response logic and its tests.
- Legacy shim symbols are NOT exported (ApiKeyAuth, AzTokenAuth, AzTokenError,
  TeamPulseAPIError, TeamPulseClient, _ClientProvider, ToolResult).
- __amplifier_module_type__ == 'tool'.

NOTE: the two count assertions here were stale on main (they asserted 11
classes / 12 names against a module that already exported 12 classes / 13
names) and failed before this change. They are corrected, not merely renumbered.
"""

_MOUNTED = [
    "TeamPulseReadTool",
    "TeamPulseWriteTool",
    "TeamPulseAskTool",
]

_OP_HANDLERS = [
    "TeamPulseConfigureTool",
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
]

_EXPECTED = sorted([*_MOUNTED, *_OP_HANDLERS, "COMPAT_TABLE", "mount"])


def test_all_contains_the_expected_names():
    """__all__ must list the 3 mounted tools, 11 op handlers, COMPAT_TABLE, mount."""
    import amplifier_module_tool_team_pulse as m

    assert sorted(m.__all__) == _EXPECTED


def test_all_has_exactly_16_names():
    """3 mounted + 11 handlers + COMPAT_TABLE + mount == 16."""
    import amplifier_module_tool_team_pulse as m

    assert len(m.__all__) == 16


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


def test_every_exported_name_is_importable():
    """Every name in __all__ resolves on the package."""
    import amplifier_module_tool_team_pulse as m

    for name in m.__all__:
        assert getattr(m, name, None) is not None, f"{name!r} is not importable"


def test_mounted_tool_classes_are_exported():
    """The 3 tools an agent actually sees must be part of the public surface."""
    import amplifier_module_tool_team_pulse as m

    for name in _MOUNTED:
        assert name in m.__all__


def test_compat_table_is_exported_and_complete():
    """COMPAT_TABLE is public: it is how old call sites get corrected."""
    from amplifier_module_tool_team_pulse import COMPAT_TABLE

    assert len(COMPAT_TABLE) == 12
    assert COMPAT_TABLE["team_pulse_get"] == ("team_pulse_read", "get")
    assert COMPAT_TABLE["team_pulse_configure"] == ("team_pulse_write", "configure")
    assert COMPAT_TABLE["team_pulse_ask"] == ("team_pulse_ask", "ask")


def test_team_pulse_status_tool_still_importable():
    """The status op handler stays importable (explicit acceptance criterion)."""
    import amplifier_module_tool_team_pulse as m

    assert "TeamPulseStatusTool" in m.__all__
