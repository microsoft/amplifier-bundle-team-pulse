# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Amplifier tool module wrapping the team-pulse lens API.

All implementation lives in :mod:`team_pulse_lib` (the standalone async client
library).  This package is a thin Amplifier adapter.

THREE tools are mounted:
    * :class:`TeamPulseReadTool`  — ``team_pulse_read``  (op: get | search |
      prefix | resources | graph | info | whoami | status)
    * :class:`TeamPulseWriteTool` — ``team_pulse_write`` (op: submit_answer |
      download_corpus | configure)
    * :class:`TeamPulseAskTool`   — ``team_pulse_ask``, UNCHANGED and
      deliberately separate: it triggers server-side LLM spend, so it stays an
      explicit, undisguised call rather than an op behind an enum.

:data:`COMPAT_TABLE` maps every formerly-separate tool name to exactly one
``(new_tool, op)`` pair.

The per-op handler classes (``TeamPulseGetTool``, ``TeamPulseConfigureTool``, …)
remain importable — they hold the per-op request/response logic — but are no
longer mounted individually.

Public surface:
    * :class:`TeamPulseAskTool`
    * :class:`TeamPulseConfigureTool`
    * :class:`TeamPulseDownloadCorpusTool`
    * :class:`TeamPulseGetTool`
    * :class:`TeamPulseGraphTool`
    * :class:`TeamPulseInfoTool`
    * :class:`TeamPulsePrefixTool`
    * :class:`TeamPulseReadTool`
    * :class:`TeamPulseResourcesTool`
    * :class:`TeamPulseSearchTool`
    * :class:`TeamPulseStatusTool`
    * :class:`TeamPulseSubmitAnswerTool`
    * :class:`TeamPulseWhoamiTool`
    * :class:`TeamPulseWriteTool`
    * :data:`COMPAT_TABLE`
    * :func:`mount`
"""

from .tool import (
    COMPAT_TABLE,
    TeamPulseAskTool,
    TeamPulseConfigureTool,
    TeamPulseDownloadCorpusTool,
    TeamPulseGetTool,
    TeamPulseGraphTool,
    TeamPulseInfoTool,
    TeamPulsePrefixTool,
    TeamPulseReadTool,
    TeamPulseResourcesTool,
    TeamPulseSearchTool,
    TeamPulseStatusTool,
    TeamPulseSubmitAnswerTool,
    TeamPulseWhoamiTool,
    TeamPulseWriteTool,
    mount,
)

__all__ = [
    "COMPAT_TABLE",
    "TeamPulseAskTool",
    "TeamPulseConfigureTool",
    "TeamPulseDownloadCorpusTool",
    "TeamPulseGetTool",
    "TeamPulseGraphTool",
    "TeamPulseInfoTool",
    "TeamPulsePrefixTool",
    "TeamPulseReadTool",
    "TeamPulseResourcesTool",
    "TeamPulseSearchTool",
    "TeamPulseStatusTool",
    "TeamPulseSubmitAnswerTool",
    "TeamPulseWhoamiTool",
    "TeamPulseWriteTool",
    "mount",
]

__amplifier_module_type__ = "tool"
