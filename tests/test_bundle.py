"""Tests for shareable bundles (:mod:`cairn.bundle`) — export, install, and a full round-trip."""

from __future__ import annotations

import json

import pytest

from cairn.bundle import export_bundle, install_bundle
from cairn.config import Profile, load_profiles
from cairn.errors import CairnError
from cairn.vault import Vault


def _source_vault(root):
    vault = Vault(root)
    vault.ensure_layout()
    (vault.skills_dir / "develop").mkdir()
    (vault.skills_dir / "develop" / "SKILL.md").write_text("dev")
    (vault.memories_dir / "conv.md").write_text("conventions")
    return vault


def _profiles():
    return {
        "base": Profile("base", ("develop",), ("conv",), "sonnet"),
        "dev": Profile(
            "dev", ("develop",), (), "opus", extends=("base",), mcp={"brave": {"command": "npx"}}
        ),
    }


def test_export_flattens_and_writes_manifest_and_assets(tmp_path):
    vault = _source_vault(tmp_path / "src")
    dest = tmp_path / "bundle"

    result = export_bundle(vault, _profiles(), "dev", dest)

    # flattened: inherits base's memory + model resolved to child's opus
    assert result.skills == ("develop",)
    assert result.memories == ("conv",)
    manifest = json.loads((dest / "cairn-bundle.json").read_text())
    entry = manifest["profiles"]["dev"]
    assert entry["memories"] == ["conv"]
    assert entry["model"] == "opus"
    assert entry["mcp"] == {"brave": {"command": "npx"}}
    # assets copied
    assert (dest / "skills" / "develop" / "SKILL.md").read_text() == "dev"
    assert (dest / "memories" / "conv.md").read_text() == "conventions"


def test_export_install_roundtrip_through_real_loader(tmp_path):
    src = _source_vault(tmp_path / "src")
    bundle = tmp_path / "bundle"
    export_bundle(src, _profiles(), "dev", bundle)

    # Install into a fresh, empty vault
    dest_vault = Vault(tmp_path / "dest")
    result = install_bundle(dest_vault, bundle)

    # Assets landed
    assert result.skills_added == ("develop",)
    assert result.memories_added == ("conv",)
    assert result.profiles_added == ("dev",)
    assert (dest_vault.skills_dir / "develop" / "SKILL.md").read_text() == "dev"

    # The appended profiles.toml parses back to the same effective definition
    installed = load_profiles(dest_vault.profiles_path)["dev"]
    assert installed.skills == ("develop",)
    assert installed.memories == ("conv",)
    assert installed.model == "opus"
    assert installed.mcp == {"brave": {"command": "npx"}}


def test_install_skips_existing_names(tmp_path):
    src = _source_vault(tmp_path / "src")
    bundle = tmp_path / "bundle"
    export_bundle(src, _profiles(), "dev", bundle)

    dest_vault = Vault(tmp_path / "dest")
    dest_vault.ensure_layout()
    (dest_vault.skills_dir / "develop").mkdir()  # already present
    (dest_vault.skills_dir / "develop" / "SKILL.md").write_text("ORIGINAL")
    dest_vault.profiles_path.write_text("[profiles.dev]\nskills = []\n")  # name collision

    result = install_bundle(dest_vault, bundle)

    assert "skill:develop" in result.skipped
    assert "profile:dev" in result.skipped
    assert result.profiles_added == ()
    # existing content untouched
    assert (dest_vault.skills_dir / "develop" / "SKILL.md").read_text() == "ORIGINAL"


def test_install_rejects_non_bundle_dir(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(CairnError, match="not a Cairn bundle"):
        install_bundle(Vault(tmp_path / "v"), tmp_path / "empty")
