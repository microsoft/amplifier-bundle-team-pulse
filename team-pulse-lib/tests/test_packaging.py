# SPDX-License-Identifier: MIT
"""Tests for package metadata (Task 10).

Verifies:
1. pyproject.toml dependency lower bounds via tomllib
2. CHANGELOG.md exists with "Semantic Versioning"
3. README.md contains "breaking-change policy" (lowercase, as in the
   'Versioning & breaking-change policy' section heading)
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# Root of the team-pulse-lib project (two levels up from tests/)
PROJECT_ROOT = Path(__file__).parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
README = PROJECT_ROOT / "README.md"

REQUIRED_DEPS = {"httpx>=0.27", "azure-identity>=1.19", "pyyaml>=6"}


def test_dependency_lower_bounds() -> None:
    """Step 1: tomllib assertion — required lower-bound deps present in pyproject."""
    with open(PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    deps: set[str] = set(data["project"]["dependencies"])
    missing = REQUIRED_DEPS - deps
    assert not missing, f"pyproject.toml [project].dependencies is missing: {missing!r}\n  actual deps: {deps!r}"


def test_changelog_exists_with_semantic_versioning() -> None:
    """Step 2: CHANGELOG.md exists and mentions 'Semantic Versioning'."""
    assert CHANGELOG.exists(), "CHANGELOG.md not found"
    content = CHANGELOG.read_text(encoding="utf-8")
    assert "Semantic Versioning" in content, "CHANGELOG.md must contain the string 'Semantic Versioning'"


def test_readme_contains_breaking_change_policy() -> None:
    """Step 3: README.md contains 'breaking-change policy' (lowercase)."""
    assert README.exists(), "README.md not found"
    content = README.read_text(encoding="utf-8")
    assert "breaking-change policy" in content, (
        "README.md must contain the string 'breaking-change policy' "
        "(as part of the 'Versioning & breaking-change policy' section heading)"
    )
