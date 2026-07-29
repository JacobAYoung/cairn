"""Tests for health checks (:mod:`cairn.doctor`)."""

from __future__ import annotations

from cairn.doctor import FAIL, OK, WARN, run_checks
from cairn.vault import Vault


def _status(checks, name):
    return next(c.status for c in checks if c.name == name)


def _seed_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.ensure_layout()
    vault.cairn_config_path.write_text(
        '[machine]\nname = "box"\n[defaults]\nprofile = "default"\n'
    )
    vault.profiles_path.write_text("[profiles.default]\nskills = []\n")
    return vault


def test_all_green_on_healthy_setup(tmp_path):
    vault = _seed_vault(tmp_path)
    project = tmp_path / "proj"
    project.mkdir()

    checks = run_checks(vault, project, ping=lambda e: True)

    assert _status(checks, "config") == OK
    assert _status(checks, "profiles") == OK
    assert _status(checks, "default-profile") == OK
    assert _status(checks, "links") == OK


def test_missing_default_profile_is_a_failure(tmp_path):
    vault = _seed_vault(tmp_path)
    vault.cairn_config_path.write_text('[defaults]\nprofile = "ghost"\n')
    project = tmp_path / "proj"
    project.mkdir()

    checks = run_checks(vault, project, ping=lambda e: True)
    assert _status(checks, "default-profile") == FAIL


def test_dangling_link_is_a_failure(tmp_path):
    vault = _seed_vault(tmp_path)
    project = tmp_path / "proj"
    (project / ".claude" / "skills").mkdir(parents=True)
    # a symlink pointing nowhere (as if the vault were unmounted)
    (project / ".claude" / "skills" / "gone").symlink_to(tmp_path / "does-not-exist")

    checks = run_checks(vault, project, ping=lambda e: True)
    assert _status(checks, "links") == FAIL


def test_invalid_config_is_a_failure(tmp_path):
    vault = _seed_vault(tmp_path)
    vault.cairn_config_path.write_text('[sync]\nmode = "rsync"\n')  # invalid mode
    project = tmp_path / "proj"
    project.mkdir()

    checks = run_checks(vault, project, ping=lambda e: True)
    assert _status(checks, "config") == FAIL


def test_unreachable_delegate_warns_not_fails(tmp_path):
    vault = _seed_vault(tmp_path)
    vault.cairn_config_path.write_text(
        '[delegate]\nenabled = true\nendpoint = "http://localhost:59999"\n'
    )
    project = tmp_path / "proj"
    project.mkdir()

    checks = run_checks(vault, project, ping=lambda e: False)
    assert _status(checks, "delegate") == WARN
