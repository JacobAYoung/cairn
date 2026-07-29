"""Tests for vault seeding (:mod:`cairn.importer`) against real temp directories."""

from __future__ import annotations

from cairn.importer import import_into_vault
from cairn.vault import Vault


def _make_skill(root, name, body="SKILL"):
    (root / name).mkdir(parents=True)
    (root / name / "SKILL.md").write_text(body)


def test_import_copies_skills_and_memories_and_reports(tmp_path):
    # Arrange: a source ~/.claude-like layout
    skills_src = tmp_path / "src-skills"
    _make_skill(skills_src, "develop")
    _make_skill(skills_src, "audit")
    memories_src = tmp_path / "src-mem"
    memories_src.mkdir()
    (memories_src / "code-conventions.md").write_text("conv")

    vault = Vault(tmp_path / "vault")

    # Act
    result = import_into_vault(vault, skills_src=skills_src, memories_src=memories_src)

    # Assert RESULT data (sorted, exact)
    assert result.skills_imported == ("audit", "develop")
    assert result.memories_imported == ("code-conventions",)
    assert result.skipped == ()

    # Assert STATE: files actually copied into the vault, content intact
    assert (vault.skills_dir / "develop" / "SKILL.md").read_text() == "SKILL"
    assert (vault.memories_dir / "code-conventions.md").read_text() == "conv"


def test_import_skips_existing_without_overwriting(tmp_path):
    # Arrange: vault already has a "develop" skill with different content
    vault = Vault(tmp_path / "vault")
    vault.ensure_layout()
    (vault.skills_dir / "develop").mkdir()
    (vault.skills_dir / "develop" / "SKILL.md").write_text("ORIGINAL")

    skills_src = tmp_path / "src"
    _make_skill(skills_src, "develop", body="NEW")

    # Act
    result = import_into_vault(vault, skills_src=skills_src)

    # Assert: reported as skipped and the original content is untouched
    assert result.skills_imported == ()
    assert result.skipped == ("skill:develop",)
    assert (vault.skills_dir / "develop" / "SKILL.md").read_text() == "ORIGINAL"


def test_import_ignores_absent_sources(tmp_path):
    vault = Vault(tmp_path / "vault")
    result = import_into_vault(vault, skills_src=tmp_path / "nope", memories_src=None)
    assert result == type(result)((), (), ())
