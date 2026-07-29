"""Tests for synced auto-memory redirection (:mod:`cairn.automemory`)."""

from __future__ import annotations

import json

from cairn.automemory import SETTING_KEY, disable, enable
from cairn.vault import Vault


def test_enable_sets_setting_and_creates_target_preserving_other_keys(tmp_path):
    # Arrange: project with a pre-existing unrelated setting
    vault = Vault(tmp_path / "vault")
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.local.json").write_text(json.dumps({"model": "opus"}))

    # Act
    target = enable(vault, project, "proj")

    # Assert: target dir created in the vault, setting points at it, other key preserved
    assert target == vault.root / "auto-memory" / "proj"
    assert target.is_dir()
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert settings[SETTING_KEY] == str(target)
    assert settings["model"] == "opus"


def test_disable_removes_setting_and_reports(tmp_path):
    vault = Vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()
    enable(vault, project, "proj")

    # Act
    removed = disable(project)

    # Assert
    assert removed is True
    settings = json.loads((project / ".claude" / "settings.local.json").read_text())
    assert SETTING_KEY not in settings


def test_disable_when_absent_returns_false(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    assert disable(project) is False
