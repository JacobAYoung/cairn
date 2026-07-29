"""Tests for the vault (:mod:`cairn.vault`) — path resolution and inventory over a real temp dir.

Per the standard, these operate on a real filesystem (temp vault) and assert resulting on-disk
state and returned data, not mocks.
"""

from __future__ import annotations

import pytest

from cairn.errors import CairnError
from cairn.vault import SUBDIRS, Vault


def _seed(root):
    """Create a small vault: two skills (dirs), two memories (.md), plus decoys to ignore."""
    (root / "skills" / "develop").mkdir(parents=True)
    (root / "skills" / "audit").mkdir(parents=True)
    (root / "skills" / "notes.txt").write_text("not a skill")  # file, must be ignored
    (root / "memories").mkdir(parents=True)
    (root / "memories" / "code-conventions.md").write_text("x")
    (root / "memories" / "git-hygiene.md").write_text("y")
    (root / "memories" / "draft.txt").write_text("not a memory")  # non-md, must be ignored


def test_ensure_layout_creates_all_subdirs(tmp_path):
    # Act
    Vault(tmp_path / "v").ensure_layout()

    # Assert STATE: every standard subdir exists on disk
    for name in SUBDIRS:
        assert (tmp_path / "v" / name).is_dir()


def test_list_skills_returns_sorted_dir_names_only(tmp_path):
    # Arrange
    _seed(tmp_path)

    # Act / Assert: sorted, files excluded
    assert Vault(tmp_path).list_skills() == ["audit", "develop"]


def test_list_memories_returns_sorted_md_stems_only(tmp_path):
    # Arrange
    _seed(tmp_path)

    # Act / Assert: sorted stems, non-.md excluded
    assert Vault(tmp_path).list_memories() == ["code-conventions", "git-hygiene"]


def test_inventory_of_absent_dirs_is_empty(tmp_path):
    vault = Vault(tmp_path / "empty")
    assert vault.list_skills() == []
    assert vault.list_memories() == []
    assert vault.exists() is False


def test_skill_path_resolves_existing_and_raises_missing(tmp_path):
    _seed(tmp_path)
    vault = Vault(tmp_path)

    # Existing -> exact path
    assert vault.skill_path("develop") == tmp_path / "skills" / "develop"
    # Missing -> CairnError naming the skill
    with pytest.raises(CairnError, match="skill 'nope' not found"):
        vault.skill_path("nope")


def test_memory_path_resolves_existing_and_raises_missing(tmp_path):
    _seed(tmp_path)
    vault = Vault(tmp_path)

    assert vault.memory_path("git-hygiene") == tmp_path / "memories" / "git-hygiene.md"
    with pytest.raises(CairnError, match="memory 'nope' not found"):
        vault.memory_path("nope")
