# SPDX-License-Identifier: MIT
"""Tests for save_config: merge semantics, migration, atomic write, directory creation."""

from __future__ import annotations

import os

import pytest
import yaml

from team_pulse_lib.config import save_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh)


def _read_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Merge semantics
# ---------------------------------------------------------------------------


class TestSaveConfigMerge:
    """Merge semantics: only provided fields are updated; other keys preserved."""

    def test_merge_preserves_client_id_when_no_api_app_id(self, tmp_path):
        """Existing client_id is preserved when api_app_id is not provided."""
        target = tmp_path / "config.yaml"
        _write_yaml(target, {"url": "https://old.example.com", "client_id": "legacy-app-123"})

        save_config("https://new.example.com", path=target)

        result = _read_yaml(target)
        assert result["url"] == "https://new.example.com"
        assert result["client_id"] == "legacy-app-123"  # preserved — not clobbered

    def test_merge_preserves_api_app_id_when_not_provided(self, tmp_path):
        """Existing api_app_id is preserved when api_app_id is not provided."""
        target = tmp_path / "config.yaml"
        _write_yaml(target, {"url": "https://old.example.com", "api_app_id": "existing-app"})

        save_config("https://new.example.com", path=target)

        result = _read_yaml(target)
        assert result["url"] == "https://new.example.com"
        assert result["api_app_id"] == "existing-app"  # preserved

    def test_merge_updates_only_url(self, tmp_path):
        """Only url is updated when no other fields are provided."""
        target = tmp_path / "config.yaml"
        _write_yaml(target, {"url": "https://old.example.com", "api_app_id": "app-123"})

        save_config("https://updated.example.com", path=target)

        result = _read_yaml(target)
        assert result["url"] == "https://updated.example.com"
        assert result["api_app_id"] == "app-123"


# ---------------------------------------------------------------------------
# Migration: client_id → api_app_id
# ---------------------------------------------------------------------------


class TestSaveConfigMigration:
    """When api_app_id is provided, the legacy client_id key is removed."""

    def test_migration_removes_client_id_when_api_app_id_provided(self, tmp_path):
        """Providing api_app_id migrates away from legacy client_id."""
        target = tmp_path / "config.yaml"
        _write_yaml(target, {"url": "https://example.com", "client_id": "old-app"})

        save_config("https://example.com", api_app_id="new-app-123", path=target)

        result = _read_yaml(target)
        assert result["api_app_id"] == "new-app-123"
        assert "client_id" not in result  # legacy key removed

    def test_migration_sets_api_app_id_on_fresh_file(self, tmp_path):
        """api_app_id is correctly written when no prior file exists."""
        target = tmp_path / "config.yaml"

        save_config("https://example.com", api_app_id="my-app-id", path=target)

        result = _read_yaml(target)
        assert result["url"] == "https://example.com"
        assert result["api_app_id"] == "my-app-id"
        assert "client_id" not in result


# ---------------------------------------------------------------------------
# First write / fresh file
# ---------------------------------------------------------------------------


class TestSaveConfigFirstWrite:
    """Correct behavior when no prior file exists."""

    def test_first_write_creates_file(self, tmp_path):
        """Creates config file when none exists."""
        target = tmp_path / "subdir" / "config.yaml"
        assert not target.exists()

        result = save_config("https://example.com", path=target)

        assert result == target
        assert target.exists()
        content = _read_yaml(target)
        assert content["url"] == "https://example.com"

    def test_first_write_strips_url_whitespace(self, tmp_path):
        """URL is stripped of leading/trailing whitespace before writing."""
        target = tmp_path / "config.yaml"

        save_config("  https://example.com  ", path=target)

        result = _read_yaml(target)
        assert result["url"] == "https://example.com"

    def test_empty_url_raises(self, tmp_path):
        """Empty URL raises ValueError."""
        target = tmp_path / "config.yaml"

        with pytest.raises(ValueError, match="url is required"):
            save_config("", path=target)

    def test_whitespace_only_url_raises(self, tmp_path):
        """Whitespace-only URL raises ValueError."""
        target = tmp_path / "config.yaml"

        with pytest.raises(ValueError, match="url is required"):
            save_config("   ", path=target)

    def test_returns_target_path(self, tmp_path):
        """Returns the path where the config was written."""
        target = tmp_path / "config.yaml"

        result = save_config("https://example.com", path=target)

        assert result == target


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------


class TestSaveConfigDirectoryCreation:
    """Parent directories are created when they do not exist."""

    def test_creates_parent_directories(self, tmp_path):
        """Creates nested parent directories as needed."""
        target = tmp_path / "deep" / "nested" / "dir" / "config.yaml"
        assert not target.parent.exists()

        save_config("https://example.com", path=target)

        assert target.exists()


# ---------------------------------------------------------------------------
# Atomic write / crash safety
# ---------------------------------------------------------------------------


class TestSaveConfigAtomicWrite:
    """Crash safety: original file intact and temp cleaned up on failure."""

    def test_atomic_write_cleans_temp_on_failure(self, tmp_path, monkeypatch):
        """If os.replace fails, temp file is removed and original is preserved."""
        target = tmp_path / "config.yaml"
        _write_yaml(target, {"url": "https://old.example.com", "client_id": "keep-me"})

        def failing_replace(src, dst):
            raise OSError("simulated disk full")

        monkeypatch.setattr(os, "replace", failing_replace)

        with pytest.raises(OSError, match="simulated disk full"):
            save_config("https://new.example.com", path=target)

        # Original file must be unchanged
        result = _read_yaml(target)
        assert result["url"] == "https://old.example.com"
        assert result["client_id"] == "keep-me"

        # No orphaned temp files must remain
        temp_files = list(tmp_path.glob("*.yaml.tmp"))
        assert not temp_files, f"Orphaned temp files found: {temp_files}"
