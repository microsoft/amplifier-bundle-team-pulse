# SPDX-License-Identifier: MIT
"""team-pulse-lib — standalone async client for the Team Pulse API.

Zero amplifier_* dependency. This package can be installed and used outside of
the Amplifier ecosystem by any Python project.

Schema v1 contract: ``metadata`` on ``AnswerUpload`` is persisted verbatim by the
    server. Session provenance (``source_session_ids``, etc.) lives inside ``metadata``.

Phase 0B public surface (this file):
    Models, errors, auth strategies, config factories, and TeamPulseClient.
"""

from team_pulse_lib._version import __version__
from team_pulse_lib.auth import ApiKeyAuth, AuthStrategy, AzCredentialAuth
from team_pulse_lib.client import TeamPulseClient  # noqa: F401
from team_pulse_lib.config import DEFAULT_API_APP_ID, ResolvedConfig, from_config, from_env, save_config
from team_pulse_lib.errors import (
    TeamPulseAPIError,
    TeamPulseAuthError,
    TeamPulseConnectionError,
    TeamPulseError,
)
from team_pulse_lib.models import AnswerUpload, ClientInfo, Question, SubmittedAnswer

__all__ = [
    "__version__",
    # client
    "TeamPulseClient",
    # models
    "Question",
    "AnswerUpload",
    "SubmittedAnswer",
    "ClientInfo",
    # errors
    "TeamPulseError",
    "TeamPulseAuthError",
    "TeamPulseAPIError",
    "TeamPulseConnectionError",
    # auth
    "AuthStrategy",
    "ApiKeyAuth",
    "AzCredentialAuth",
    # config
    "from_env",
    "from_config",
    "save_config",
    "ResolvedConfig",
    "DEFAULT_API_APP_ID",
]
