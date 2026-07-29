"""Tests for starter-config scaffolding (:mod:`cairn.scaffold`)."""

from __future__ import annotations

from cairn.config import load_cairn_config
from cairn.scaffold import write_starter_config
from cairn.vault import Vault


def test_writes_both_files_with_machine_and_sync_and_is_loadable(tmp_path):
    vault = Vault(tmp_path / "vault")

    created = write_starter_config(vault, machine="desktop", sync_mode="syncthing")

    assert created == ["cairn.toml", "profiles.toml"]
    # The generated cairn.toml round-trips through the real loader with the expected values
    config = load_cairn_config(vault.cairn_config_path, default_machine_name="x")
    assert config.machine.name == "desktop"
    assert config.sync.mode == "syncthing"
    assert config.default_profile == "default"


def test_is_non_destructive_on_rerun(tmp_path):
    vault = Vault(tmp_path / "vault")
    write_starter_config(vault, machine="desktop", sync_mode="off")
    vault.cairn_config_path.write_text('[machine]\nname = "edited"\n')

    # Act: rerun
    created = write_starter_config(vault, machine="desktop", sync_mode="off")

    # Assert: nothing recreated, the user's edit survives
    assert created == []
    assert 'name = "edited"' in vault.cairn_config_path.read_text()
