# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Fail-before test for the 12 -> 3 tool consolidation.

Two load-bearing assertions, both of which FAIL against the pre-consolidation
module (which mounted 12 tools and had no compatibility table):

1. ``mount()`` registers EXACTLY three tools: team_pulse_read,
   team_pulse_write, team_pulse_ask.
2. Every formerly-separate tool name that had >= 1 recorded call resolves
   through :data:`COMPAT_TABLE` to exactly one (new tool, op) pair, and that op
   really exists on that tool.

USAGE, 30-day window, 9 users (source: W/_dashboard/TOOL-SKILL-USAGE.md).
This is the population the consolidation must not break:

    | tool                       | calls | distinct users |
    |----------------------------|------:|---------------:|
    | team_pulse_get             |   596 |              8 |
    | team_pulse_search          |   566 |              9 |
    | team_pulse_info            |    87 |              8 |
    | team_pulse_status          |    53 |              8 |
    | team_pulse_prefix          |    30 |              7 |
    | team_pulse_resources       |    30 |              6 |
    | team_pulse_whoami          |    16 |              6 |
    | team_pulse_download_corpus |     5 |              3 |
    | team_pulse_graph           |     2 |              2 |

Zero-in-window: team_pulse_configure (2 calls all-time),
team_pulse_submit_answer (0 all-time), team_pulse_ask (5 all-time — UNCHANGED,
not consolidated).
"""

from __future__ import annotations

import json
from typing import Any

from amplifier_module_tool_team_pulse.tool import (
    COMPAT_TABLE,
    TeamPulseAskTool,
    TeamPulseReadTool,
    TeamPulseWriteTool,
    mount,
)

#: tool name -> (calls, distinct users) over the 30-day window.
USAGE_30D: dict[str, tuple[int, int]] = {
    "team_pulse_get": (596, 8),
    "team_pulse_search": (566, 9),
    "team_pulse_info": (87, 8),
    "team_pulse_status": (53, 8),
    "team_pulse_prefix": (30, 7),
    "team_pulse_resources": (30, 6),
    "team_pulse_whoami": (16, 6),
    "team_pulse_download_corpus": (5, 3),
    "team_pulse_graph": (2, 2),
}

#: Names with zero calls in the window but still part of the old surface.
ZERO_IN_WINDOW: tuple[str, ...] = (
    "team_pulse_configure",
    "team_pulse_submit_answer",
    "team_pulse_ask",
)

EXPECTED_MOUNTED: set[str] = {"team_pulse_read", "team_pulse_write", "team_pulse_ask"}


class _FakeCoordinator:
    def __init__(self) -> None:
        self.mounted: list[tuple[str, Any, str]] = []

    async def mount(self, kind: str, tool: Any, name: str) -> None:
        self.mounted.append((kind, tool, name))


async def _mounted() -> dict[str, Any]:
    coord = _FakeCoordinator()
    await mount(coord, {})
    return {name: tool for _, tool, name in coord.mounted}


# ---------------------------------------------------------------------------
# 1. Exactly three tools
# ---------------------------------------------------------------------------


async def test_exactly_three_tools_are_mounted() -> None:
    """mount() registers exactly 3 tools — no more, no fewer."""
    tools = await _mounted()
    assert len(tools) == 3, f"expected 3 mounted tools, got {len(tools)}: {sorted(tools)}"


async def test_mounted_tool_names_are_read_write_ask() -> None:
    tools = await _mounted()
    assert set(tools) == EXPECTED_MOUNTED


async def test_no_legacy_tool_name_is_still_mounted() -> None:
    """None of the 12 old names may remain mounted — except team_pulse_ask."""
    tools = await _mounted()
    legacy = (set(USAGE_30D) | set(ZERO_IN_WINDOW)) - {"team_pulse_ask"}
    assert legacy.isdisjoint(set(tools))


# ---------------------------------------------------------------------------
# 2. Compatibility table resolves every name that had calls
# ---------------------------------------------------------------------------


async def test_every_used_tool_name_resolves_to_a_live_op() -> None:
    """Each of the 9 names with >=1 call maps to one (tool, op) that exists."""
    tools = await _mounted()
    for old_name in USAGE_30D:
        assert old_name in COMPAT_TABLE, f"{old_name} missing from COMPAT_TABLE"
        new_tool, op = COMPAT_TABLE[old_name]
        assert new_tool in tools, f"{old_name} -> unmounted tool {new_tool!r}"
        ops = getattr(tools[new_tool], "_OPS", None)
        if ops is None:  # team_pulse_ask: its own tool, no op enum
            assert new_tool == "team_pulse_ask"
            continue
        assert op in ops, f"{old_name} -> {new_tool}(op={op!r}) but op does not exist"


def test_compat_table_covers_every_former_tool_name() -> None:
    """All 12 former names are in the table — the 9 used plus the 3 unused."""
    assert set(COMPAT_TABLE) == set(USAGE_30D) | set(ZERO_IN_WINDOW)
    assert len(COMPAT_TABLE) == 12


def test_compat_table_maps_each_name_to_exactly_one_pair() -> None:
    for old_name, pair in COMPAT_TABLE.items():
        assert isinstance(pair, tuple) and len(pair) == 2, f"{old_name}: {pair!r}"
        new_tool, op = pair
        assert new_tool in EXPECTED_MOUNTED
        assert isinstance(op, str) and op


def test_compat_table_targets_are_unique_per_name() -> None:
    """No two former names collapse onto the same (tool, op) pair."""
    pairs = list(COMPAT_TABLE.values())
    assert len(pairs) == len(set(pairs))


# ---------------------------------------------------------------------------
# 3. team_pulse_ask is UNCHANGED and still its own tool
# ---------------------------------------------------------------------------


async def test_ask_remains_its_own_unconsolidated_tool() -> None:
    """ask triggers server-side LLM spend; it must never hide behind an op enum."""
    tools = await _mounted()
    assert isinstance(tools["team_pulse_ask"], TeamPulseAskTool)
    assert COMPAT_TABLE["team_pulse_ask"] == ("team_pulse_ask", "ask")
    assert "ask" not in TeamPulseReadTool._OPS
    assert "ask" not in TeamPulseWriteTool._OPS


async def test_ask_schema_is_unchanged() -> None:
    """ask keeps prompt/focus with prompt required — no op key added."""
    tools = await _mounted()
    schema = tools["team_pulse_ask"].input_schema
    assert set(schema["properties"]) == {"prompt", "focus"}
    assert schema["required"] == ["prompt"]


# ---------------------------------------------------------------------------
# 4. The op enums match the compatibility table exactly
# ---------------------------------------------------------------------------


def test_read_ops_are_exactly_the_documented_eight() -> None:
    assert set(TeamPulseReadTool._OPS) == {
        "get",
        "search",
        "prefix",
        "resources",
        "graph",
        "info",
        "whoami",
        "status",
    }


def test_write_ops_are_exactly_the_documented_three() -> None:
    assert set(TeamPulseWriteTool._OPS) == {
        "submit_answer",
        "download_corpus",
        "configure",
    }


def test_op_enum_in_schema_matches_the_dispatch_table() -> None:
    """A schema that advertises an op the dispatcher cannot run is a silent trap."""
    for cls in (TeamPulseReadTool, TeamPulseWriteTool):
        tool = cls(None)
        assert tool.input_schema["properties"]["op"]["enum"] == list(cls._OPS)
        assert tool.input_schema["required"] == ["op"]


def test_every_op_appears_in_the_compat_table() -> None:
    """No op exists that no former tool name maps onto (and vice versa)."""
    declared = {(tool, op) for tool, op in COMPAT_TABLE.values()}
    live = {("team_pulse_read", op) for op in TeamPulseReadTool._OPS}
    live |= {("team_pulse_write", op) for op in TeamPulseWriteTool._OPS}
    live |= {("team_pulse_ask", "ask")}
    assert declared == live


# ---------------------------------------------------------------------------
# 5. Rendered-surface budget — stops the surface silently regrowing
# ---------------------------------------------------------------------------

#: Chars of provider-facing payload the three tools may occupy in total.
#: Measured live (fresh AMPLIFIER_HOME, 20-entry app list): 9,967 before this
#: change across 12 tools; the budget is the goal's <= 4,000 target.
RENDERED_BUDGET = 4000


def _rendered_chars(tool: Any) -> int:
    """name + description + input_schema JSON — the payload a provider receives."""
    return len(tool.name) + len(tool.description) + len(json.dumps(tool.input_schema, ensure_ascii=False))


async def test_rendered_surface_is_within_budget() -> None:
    tools = await _mounted()
    total = sum(_rendered_chars(t) for t in tools.values())
    assert total <= RENDERED_BUDGET, (
        f"team-pulse rendered tool surface is {total} chars, over the "
        f"{RENDERED_BUDGET} budget: " + ", ".join(f"{n}={_rendered_chars(t)}" for n, t in sorted(tools.items()))
    )
