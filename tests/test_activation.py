"""Tests for profile activation (:mod:`cairn.activation`).

The pure resolver is asserted on exact merged data. The filesystem effect is exercised against a
real temp vault + project and asserts on-disk state: which symlinks exist and where they point,
the exact settings.local.json contents (model set AND other keys preserved), manifest contents,
and — critically — that ``clear`` removes only what Cairn created and restores the prior model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairn.activation import (
    activate,
    deactivate,
    read_state,
    resolve_bundle,
)
from cairn.config import Profile
from cairn.errors import CairnError
from cairn.vault import Vault

NOW = "2026-07-29T12:00:00"


def _vault(root: Path) -> Vault:
    for skill in ("develop", "audit", "web-notes"):
        (root / "skills" / skill).mkdir(parents=True)
    (root / "memories").mkdir(parents=True)
    for mem in ("code-conventions", "git-hygiene"):
        (root / "memories" / f"{mem}.md").write_text(f"# {mem}\n")
    return Vault(root)


def _profiles() -> dict[str, Profile]:
    return {
        "dev-heavy": Profile(
            name="dev-heavy",
            skills=("develop", "audit"),
            memories=("code-conventions",),
            model="opus",
            delegate=True,
        ),
        "research": Profile(
            name="research",
            skills=("web-notes", "develop"),
            memories=("git-hygiene",),
            model="sonnet",
        ),
    }


# --- resolve_bundle (pure) ----------------------------------------------------------------


def test_resolve_merges_skills_memories_and_takes_last_model():
    # Act: merge two profiles; "develop" is shared -> must appear once, order preserved
    bundle = resolve_bundle(_profiles(), ["dev-heavy", "research"])

    # Assert exact merged data
    assert bundle.profiles == ("dev-heavy", "research")
    assert bundle.skills == ("develop", "audit", "web-notes")  # dedup, first-seen order
    assert bundle.memories == ("code-conventions", "git-hygiene")
    assert bundle.model == "sonnet"  # last profile's model wins


def test_resolve_unknown_profile_raises_and_lists_available():
    with pytest.raises(CairnError, match="unknown profile.*nope"):
        resolve_bundle(_profiles(), ["nope"])


def test_resolve_empty_raises():
    with pytest.raises(CairnError, match="no profile"):
        resolve_bundle(_profiles(), [])


# --- activate (filesystem) ----------------------------------------------------------------


def test_activate_creates_links_model_and_manifest(tmp_path):
    # Arrange
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()
    bundle = resolve_bundle(_profiles(), ["dev-heavy"])

    # Act
    result = activate(project, vault, bundle, now=NOW)

    # Assert RESULT data
    assert result.linked_skills == ("develop", "audit")
    assert result.linked_memories == ("code-conventions",)
    assert result.model == "opus"

    # Assert STATE: skill symlink points into the vault
    skill_link = project / ".claude" / "skills" / "develop"
    assert skill_link.is_symlink()
    assert skill_link.resolve() == (vault.root / "skills" / "develop").resolve()
    # memory linked into .claude/rules/ as <name>.md
    mem_link = project / ".claude" / "rules" / "code-conventions.md"
    assert mem_link.is_symlink()
    assert mem_link.resolve() == (vault.root / "memories" / "code-conventions.md").resolve()

    # Assert STATE: model merged into settings.local.json
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert settings["model"] == "opus"

    # Assert STATE: manifest records exactly the links it made + model bookkeeping
    manifest = json.loads((project / ".cairn" / "manifest.json").read_text())
    assert set(manifest["links"]) == {
        ".claude/skills/develop",
        ".claude/skills/audit",
        ".claude/rules/code-conventions.md",
    }
    assert manifest["model_written"] is True
    assert manifest["prior_had_model"] is False

    # Assert STATE: human-facing state
    assert read_state(project) == {"profiles": ["dev-heavy"], "activated_at": NOW}


def test_activate_preserves_existing_settings_keys(tmp_path):
    # Arrange: a project that already has settings.local.json with an unrelated key
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.local.json").write_text(
        json.dumps({"autoMemoryEnabled": False})
    )
    bundle = resolve_bundle(_profiles(), ["dev-heavy"])

    # Act
    activate(project, vault, bundle, now=NOW)

    # Assert: model added AND the pre-existing key survived (didn't clobber)
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert settings == {"autoMemoryEnabled": False, "model": "opus"}


def test_activate_validates_before_touching_disk(tmp_path):
    # Arrange: a profile referencing a skill that isn't in the vault
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()
    profiles = {"broken": Profile("broken", ("ghost-skill",), (), None, False)}
    bundle = resolve_bundle(profiles, ["broken"])

    # Act / Assert: raises and creates NOTHING
    with pytest.raises(CairnError, match="skill 'ghost-skill' not found"):
        activate(project, vault, bundle, now=NOW)
    assert not (project / ".claude").exists()
    assert not (project / ".cairn").exists()


def test_activate_refuses_to_clobber_handplaced_file(tmp_path):
    # Arrange: a real (non-symlink) file already sits where a skill link would go
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    (project / ".claude" / "skills" / "develop").mkdir(parents=True)
    (project / ".claude" / "skills" / "develop" / "SKILL.md").write_text("hand-made")
    bundle = resolve_bundle(_profiles(), ["dev-heavy"])

    with pytest.raises(CairnError, match="refusing to overwrite"):
        activate(project, vault, bundle, now=NOW)


def test_reactivation_replaces_prior_links(tmp_path):
    # Arrange
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()

    # Act: activate dev-heavy, then research
    activate(project, vault, resolve_bundle(_profiles(), ["dev-heavy"]), now=NOW)
    activate(project, vault, resolve_bundle(_profiles(), ["research"]), now=NOW)

    # Assert: dev-heavy-only link ("audit") is gone; research's ("web-notes") present
    assert not (project / ".claude" / "skills" / "audit").exists()
    assert (project / ".claude" / "skills" / "web-notes").is_symlink()
    # model reflects the new profile
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert settings["model"] == "sonnet"
    assert read_state(project)["profiles"] == ["research"]


# --- deactivate ---------------------------------------------------------------------------


def test_deactivate_removes_only_cairn_links_and_restores_model(tmp_path):
    # Arrange: pre-existing settings WITH a model, plus a hand-placed rule that Cairn must not touch
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.local.json").write_text(json.dumps({"model": "haiku"}))
    (project / ".claude" / "rules").mkdir()
    (project / ".claude" / "rules" / "handmade.md").write_text("mine")

    activate(project, vault, resolve_bundle(_profiles(), ["dev-heavy"]), now=NOW)

    # Act
    profiles = deactivate(project)

    # Assert: returns the profiles that were active
    assert profiles == ("dev-heavy",)
    # Cairn's links removed
    assert not (project / ".claude" / "skills" / "develop").exists()
    assert not (project / ".claude" / "rules" / "code-conventions.md").exists()
    # hand-placed file untouched
    assert (project / ".claude" / "rules" / "handmade.md").read_text() == "mine"
    # prior model restored (not left as "opus", not removed)
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert settings["model"] == "haiku"
    # state cleared
    assert read_state(project) is None


def test_deactivate_removes_model_key_when_none_existed_before(tmp_path):
    # Arrange: no model before activation
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()
    activate(project, vault, resolve_bundle(_profiles(), ["dev-heavy"]), now=NOW)

    # Act
    deactivate(project)

    # Assert: the model key we added is gone again
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert "model" not in settings


def test_deactivate_without_manifest_is_noop(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    assert deactivate(project) == ()
