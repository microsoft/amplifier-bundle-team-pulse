# SPDX-License-Identifier: MIT
"""Single config-resolution path for team-pulse-lib.

Precedence (high → low):
  1. Explicit constructor arg [Phase 0B] — applied by the client, not this module.
  2. Environment variable
  3. ~/.amplifier/team-pulse/config.yaml (the file team_pulse_configure writes)
  4. Shipped default

This module owns tiers 2–4.  Tier 1 is applied by TeamPulseClient in Phase 0B.

Auth strategy is INFERRED from credentials present (key-wins rule) with a
fail-loud force override.  The legacy auth_mode field is honored only for
migration purposes and is never a silent behavior change.
"""

from __future__ import annotations

import os
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from team_pulse_lib.auth import (
    ApiKeyAuth,
    AuthStrategy,
    AzCredentialAuth,
    is_valid_key,
)

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------

ENV_URL: str = "AMPLIFIER_TEAM_PULSE_URL"
ENV_KEY: str = "AMPLIFIER_TEAM_PULSE_KEY"
ENV_API_APP_ID: str = "AMPLIFIER_TEAM_PULSE_API_APP_ID"
ENV_AUTH_MODE: str = "AMPLIFIER_TEAM_PULSE_AUTH_MODE"  # legacy — migration only

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_API_APP_ID: str = "dea6e881-4cd8-4aba-87da-a52ff3e19bce"

# ---------------------------------------------------------------------------
# One-time deprecation guard (tests clear this between runs)
# ---------------------------------------------------------------------------

_WARNED_ONCE: set[str] = set()

_CLIENT_ID_DEPRECATION: str = (
    "'client_id' is a deprecated alias for 'api_app_id'. "
    "It will be removed in the next minor release — please rename it to 'api_app_id'."
)
_AUTH_MODE_DEPRECATION: str = (
    "'auth_mode' is deprecated. It is honored only for migration; "
    "auth is now inferred from credentials present. "
    "Use the 'force' parameter to pin a strategy explicitly."
)


def _warn_once(key: str, message: str) -> None:
    """Emit *message* as a DeprecationWarning exactly once per *key*."""
    if key in _WARNED_ONCE:
        return
    _WARNED_ONCE.add(key)
    warnings.warn(message, DeprecationWarning, stacklevel=3)


# ---------------------------------------------------------------------------
# Internal settings dataclass
# ---------------------------------------------------------------------------


@dataclass
class _Settings:
    """Resolved configuration values from env / file / defaults."""

    base_url: str
    api_app_id: str
    api_key: str | None
    legacy_auth_mode: str | None


# ---------------------------------------------------------------------------
# File path helpers
# ---------------------------------------------------------------------------


def _user_config_path() -> Path:
    """Return the path to the user's team-pulse config file.

    Honors ``AMPLIFIER_TEAM_PULSE_DIR`` so tests and CI can point elsewhere.
    Mirrors ``endpoint_config.config_path()`` so an in-place upgrade reads the
    same file that ``team_pulse_configure`` wrote.
    """
    env_dir = os.environ.get("AMPLIFIER_TEAM_PULSE_DIR", "").strip()
    base = Path(env_dir) if env_dir else Path.home() / ".amplifier" / "team-pulse"
    return base / "config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load *path* as YAML, returning an empty dict on any failure."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        return {}
    return raw if isinstance(raw, dict) else {}


# ---------------------------------------------------------------------------
# Core resolution logic
# ---------------------------------------------------------------------------


def _resolve_settings(file_dict: dict[str, Any]) -> _Settings:
    """Resolve settings from env vars and *file_dict* (already loaded YAML).

    Precedence for each field: env var > file key > default.
    """
    # --- base_url ---
    env_url = os.environ.get(ENV_URL, "")
    base_url = (env_url or str(file_dict.get("url") or "")).strip()

    # --- api_app_id ---
    # Precedence: env var > "api_app_id" key in file > "client_id" key in file (deprecated) > DEFAULT.
    # Empty / whitespace-only values at any tier are treated as "not present" and fall through
    # to the next tier.  This prevents a config file with api_app_id: "" from silently bypassing
    # the DEFAULT and producing scope "api:///.default" (which Entra rejects: AADSTS500011).
    env_app = os.environ.get(ENV_API_APP_ID, "").strip()
    if env_app:
        api_app_id = env_app
    elif "api_app_id" in file_dict and (v := str(file_dict["api_app_id"] or "").strip()):
        api_app_id = v
    elif "client_id" in file_dict and (v := str(file_dict["client_id"] or "").strip()):
        _warn_once("client_id", _CLIENT_ID_DEPRECATION)
        api_app_id = v
    else:
        api_app_id = DEFAULT_API_APP_ID

    # --- api_key ---
    env_key = os.environ.get(ENV_KEY)
    api_key: str | None = env_key if env_key not in (None, "") else file_dict.get("key")

    # --- legacy_auth_mode ---
    env_mode = os.environ.get(ENV_AUTH_MODE)
    legacy_auth_mode: str | None = env_mode or file_dict.get("auth_mode") or None

    return _Settings(
        base_url=base_url,
        api_app_id=api_app_id,
        api_key=api_key,
        legacy_auth_mode=legacy_auth_mode,
    )


# ---------------------------------------------------------------------------
# ResolvedConfig (public output — Phase 0B consumes this)
# ---------------------------------------------------------------------------


@dataclass
class ResolvedConfig:
    """Configuration resolved and ready for client construction.

    The secret API key is never a named field — it lives inside
    ``ApiKeyAuth._key`` (private) and never appears in ``repr()``.
    """

    base_url: str
    auth: AuthStrategy
    auth_mode: Literal["key", "az"]
    api_app_id: str | None
    forced: bool


# ---------------------------------------------------------------------------
# Strategy selection
# ---------------------------------------------------------------------------


def _select(
    settings: _Settings,
    force: str | None,
    credential: Any | None,
) -> tuple[AuthStrategy, Literal["key", "az"], bool]:
    """Return (strategy, auth_mode, forced) using: force > legacy > key-wins."""
    if force is not None:
        if force not in ("key", "az"):
            raise ValueError(f"force must be 'key' or 'az' (exact, lowercase), got {force!r}")
        mode: Literal["key", "az"] = force  # type: ignore[assignment]
        forced = True
    elif settings.legacy_auth_mode:
        legacy = settings.legacy_auth_mode.strip().lower()
        if legacy not in ("key", "az"):
            raise ValueError(f"auth_mode must be 'key' or 'az', got {settings.legacy_auth_mode!r}")
        _warn_once("auth_mode", _AUTH_MODE_DEPRECATION)
        mode = legacy  # type: ignore[assignment]
        forced = True
    else:
        mode = "key" if is_valid_key(settings.api_key) else "az"
        forced = False

    if mode == "key":
        auth: AuthStrategy = ApiKeyAuth(settings.api_key)
    else:
        auth = AzCredentialAuth(api_app_id=settings.api_app_id, credential=credential)

    return auth, mode, forced


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------


def _build_resolved(
    settings: _Settings,
    *,
    force: str | None,
    credential: Any | None,
) -> ResolvedConfig:
    """Build a ``ResolvedConfig``, raising ``ValueError`` if ``base_url`` is absent."""
    if not settings.base_url:
        raise ValueError("base_url is required: set AMPLIFIER_TEAM_PULSE_URL or 'url' in your config file.")
    auth, mode, forced = _select(settings, force, credential)
    return ResolvedConfig(
        base_url=settings.base_url,
        auth=auth,
        auth_mode=mode,
        api_app_id=settings.api_app_id,
        forced=forced,
    )


# ---------------------------------------------------------------------------
# Public factories
# ---------------------------------------------------------------------------


def from_env(
    force: str | None = None,
    *,
    credential: Any | None = None,
) -> ResolvedConfig:
    """Resolve configuration from env vars, user config file, and defaults.

    Parameters
    ----------
    force:
        Pin to exactly ``'key'`` or ``'az'``; any other value raises
        ``ValueError`` immediately.
    credential:
        Azure credential to inject (must-fix 3).  ``None`` → lazy
        ``DefaultAzureCredential`` (constructed only if Azure mode is selected).
    """
    return _build_resolved(
        _resolve_settings(_load_yaml(_user_config_path())),
        force=force,
        credential=credential,
    )


def save_config(
    url: str,
    *,
    api_app_id: str | None = None,
    path: str | Path | None = None,
) -> Path:
    """Write configuration to a YAML file (merge semantics).

    Reads any existing file first and merges: only the fields explicitly
    provided are updated; all other keys in the file are preserved.  The
    write is atomic — a crash mid-write leaves the original file intact.

    Parameters
    ----------
    url:
        Team Pulse server URL.  Required.
    api_app_id:
        Azure AD app ID.  When provided, ``api_app_id`` is set and the legacy
        ``client_id`` key is removed.  When absent, any existing app-id key
        (``api_app_id`` or ``client_id``) is preserved unchanged.
    path:
        Where to write the file.  Defaults to the user config path returned by
        ``_user_config_path()`` (``~/.amplifier/team-pulse/config.yaml`` unless
        ``AMPLIFIER_TEAM_PULSE_DIR`` is set).

    Returns
    -------
    pathlib.Path
        The path where the configuration was written.
    """
    if not url or not url.strip():
        raise ValueError("url is required and must not be empty.")
    target = Path(path) if path is not None else _user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    # READ existing file (merge semantics: preserve keys not provided)
    current = _load_yaml(target)

    # MERGE: set only the fields the caller explicitly provided
    current["url"] = url.strip()
    if api_app_id is not None:
        current["api_app_id"] = api_app_id
        current.pop("client_id", None)  # migrate away from legacy key
    # else: preserve existing app-id key (api_app_id or legacy client_id)

    # ATOMIC WRITE: tempfile → write → os.replace (crash-safe)
    fd, temp_path_str = tempfile.mkstemp(dir=target.parent, suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(current, fh)
        os.replace(temp_path_str, target)
    except BaseException:
        try:
            os.unlink(temp_path_str)
        except OSError:
            pass
        raise

    return target


def from_config(
    path: str | Path,
    force: str | None = None,
    *,
    credential: Any | None = None,
) -> ResolvedConfig:
    """Resolve configuration from env vars, a given YAML file, and defaults.

    File format is backward-compatible: keys ``url``, ``api_app_id``
    (or deprecated ``client_id``), ``key``, ``auth_mode``.

    Parameters
    ----------
    path:
        Path to a YAML config file.
    force:
        Pin to exactly ``'key'`` or ``'az'``; any other value raises
        ``ValueError`` immediately.
    credential:
        Azure credential to inject.  ``None`` → lazy ``DefaultAzureCredential``.
    """
    return _build_resolved(
        _resolve_settings(_load_yaml(Path(path))),
        force=force,
        credential=credential,
    )


def from_args(
    *,
    base_url: str | None = None,
    key: str | None = None,
    force: str | None = None,
    credential: Any | None = None,
) -> ResolvedConfig:
    """Resolve configuration with optional explicit argument overrides.

    This is the **single resolution home** for :meth:`TeamPulseClient.connect`.
    All precedence rules, auth inference, and provenance labelling live here.

    Precedence (high → low):

    1. Explicit arg (``base_url``, ``key``)
    2. Environment variable (``AMPLIFIER_TEAM_PULSE_URL``, ``AMPLIFIER_TEAM_PULSE_KEY``)
    3. User config file (``~/.amplifier/team-pulse/config.yaml``)
    4. Shipped default (``api_app_id`` only → ``DEFAULT_API_APP_ID``)

    Parameters
    ----------
    base_url:
        Explicit server URL override.  When provided, wins over
        ``AMPLIFIER_TEAM_PULSE_URL`` and the config file's ``url`` key.
        ``None`` means "not supplied — fall through to env/file".
    key:
        Explicit API key override.  When provided, wins over
        ``AMPLIFIER_TEAM_PULSE_KEY`` and the config file's ``key`` field.
        A ``tp_``-prefixed non-empty value selects ``ApiKeyAuth``; anything
        else (including ``None`` = not supplied) falls back to the key-wins
        inference rule.
    force:
        Pin to exactly ``'key'`` or ``'az'``; any other value raises
        ``ValueError`` immediately.
    credential:
        Azure credential to inject.  ``None`` → lazy ``DefaultAzureCredential``.
    """
    file_dict = _load_yaml(_user_config_path())
    settings = _resolve_settings(file_dict)
    # Apply explicit arg overrides — these win over env vars and config file.
    if base_url is not None:
        settings.base_url = base_url.strip()
    if key is not None:
        settings.api_key = key
    return _build_resolved(settings, force=force, credential=credential)
