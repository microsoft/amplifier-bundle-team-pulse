# SPDX-License-Identifier: MIT
"""S8: Public surface contract tests.

Verifies that team_pulse_lib exposes exactly the Phase 0B public API,
which adds TeamPulseClient to the Phase 0A surface.

The 17 names that make up the Phase 0B surface:
  - 1 version string
  - 4 model classes (Question, AnswerUpload, SubmittedAnswer, ClientInfo)
  - 4 exception classes
  - 3 auth exports (AuthStrategy, ApiKeyAuth, AzCredentialAuth)
  - 4 config exports (from_env, from_config, save_config, ResolvedConfig)
  - 1 client class (TeamPulseClient)
"""

from __future__ import annotations

import pytest

import team_pulse_lib as tpl

_EXPECTED: list[str] = [
    "__version__",
    # client (Phase 0B)
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


@pytest.mark.parametrize("name", _EXPECTED)
def test_expected_name_is_exported(name: str) -> None:
    """Every Phase 0B name must be accessible as an attribute of team_pulse_lib."""
    assert hasattr(tpl, name), f"team_pulse_lib is missing Phase 0B export: {name!r}"


def test_all_matches_expected() -> None:
    """__all__ must contain exactly the 17 Phase 0B names (no more, no less)."""
    assert set(tpl.__all__) == set(_EXPECTED), (
        f"__all__ mismatch.\n"
        f"  Extra:   {set(tpl.__all__) - set(_EXPECTED)}\n"
        f"  Missing: {set(_EXPECTED) - set(tpl.__all__)}"
    )


def test_client_is_exported() -> None:
    """TeamPulseClient must be exported in Phase 0B."""
    assert hasattr(tpl, "TeamPulseClient"), (
        "TeamPulseClient is missing from team_pulse_lib — it is part of the Phase 0B public API"
    )


def test_unsupported_error_is_gone() -> None:
    """TeamPulseUnsupportedError must no longer be importable from team_pulse_lib."""
    assert not hasattr(tpl, "TeamPulseUnsupportedError")
