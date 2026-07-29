"""Tests for the SessionStart hook logic (:mod:`cairn.session_start`)."""

from __future__ import annotations

from pathlib import Path

from cairn.activation import activate, read_state, resolve_bundle
from cairn.config import (
    BridgeConfig,
    CairnConfig,
    DelegateConfig,
    MachineConfig,
    Profile,
    SyncConfig,
)
from cairn.session_start import build_session_start_output
from cairn.vault import Vault

NOW = "2026-07-29T12:00:00"


def _vault(root: Path) -> Vault:
    (root / "skills" / "develop").mkdir(parents=True)
    (root / "memories").mkdir(parents=True)
    return Vault(root)


def _config(default_profile):
    return CairnConfig(
        machine=MachineConfig("box"),
        sync=SyncConfig(),
        delegate=DelegateConfig(),
        bridge=BridgeConfig(),
        default_profile=default_profile,
    )


def _profiles():
    return {"default": Profile("default", ("develop",), (), "opus", False)}


def test_auto_activates_default_when_nothing_active(tmp_path):
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()

    output = build_session_start_output(
        vault, project, _config("default"), _profiles(), now=NOW
    )

    # Side effect: the default profile was actually activated (skill linked)
    assert (project / ".claude" / "skills" / "develop").is_symlink()
    assert read_state(project)["profiles"] == ["default"]
    # Output tells Claude to reload skills and names the active profile
    hook = output["hookSpecificOutput"]
    assert hook["reloadSkills"] is True
    assert "default" in hook["additionalContext"]


def test_respects_existing_activation_and_does_not_switch_to_default(tmp_path):
    vault = _vault(tmp_path / "vault")
    (vault.root / "skills" / "other").mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    # Pre-activate a different profile explicitly
    profiles = {**_profiles(), "explicit": Profile("explicit", ("other",), (), "sonnet", False)}
    activate(project, vault, resolve_bundle(profiles, ["explicit"]), now=NOW)

    output = build_session_start_output(vault, project, _config("default"), profiles, now=NOW)

    # The explicit profile stays; default is NOT force-activated over it
    assert read_state(project)["profiles"] == ["explicit"]
    assert "explicit" in output["hookSpecificOutput"]["additionalContext"]
    assert (project / ".claude" / "skills" / "develop").exists() is False


def test_injects_latest_brief(tmp_path):
    from cairn.checkpoints import write_checkpoint

    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()
    write_checkpoint(vault, "proj", "resume the refactor", machine="box", now=NOW)

    output = build_session_start_output(vault, project, _config(None), _profiles(), now=NOW)

    assert "resume the refactor" in output["hookSpecificOutput"]["additionalContext"]


def test_empty_when_nothing_to_contribute(tmp_path):
    vault = _vault(tmp_path / "vault")
    project = tmp_path / "proj"
    project.mkdir()

    # No default configured, nothing active, no checkpoint -> empty payload
    assert build_session_start_output(vault, project, _config(None), _profiles(), now=NOW) == {}
