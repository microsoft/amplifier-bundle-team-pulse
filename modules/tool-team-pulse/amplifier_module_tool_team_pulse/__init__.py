# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Amplifier tool module wrapping the team-pulse lens API.

All implementation lives in :mod:`team_pulse_lib` (the standalone async client
library).  This package is a thin Amplifier adapter that exposes 11 tool classes
and a :func:`mount` entry point — nothing else.

Public surface:
    * :class:`TeamPulseAskTool`
    * :class:`TeamPulseConfigureTool`
    * :class:`TeamPulseDownloadAnswersTool`
    * :class:`TeamPulseDownloadCorpusTool`
    * :class:`TeamPulseGetTool`
    * :class:`TeamPulseGraphTool`
    * :class:`TeamPulseInfoTool`
    * :class:`TeamPulsePrefixTool`
    * :class:`TeamPulseResourcesTool`
    * :class:`TeamPulseSearchTool`
    * :class:`TeamPulseStatusTool`
    * :class:`TeamPulseSubmitAnswerTool`
    * :class:`TeamPulseWhoamiTool`
    * :func:`mount`
"""

from .tool import (
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

__all__ = [
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

__amplifier_module_type__ = "tool"
