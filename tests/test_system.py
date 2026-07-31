"""Tests for host/environment lookups (:mod:`cairn.system`)."""

from __future__ import annotations

from pathlib import Path

from cairn import system


def test_vault_root_honors_cairn_home(monkeypatch):
    # Arrange
    monkeypatch.setenv(system.CAIRN_HOME_ENV, "~/custom-vault")

    # Act / Assert: env override wins and ~ is expanded
    assert system.default_vault_root() == Path("~/custom-vault").expanduser()


def test_vault_root_defaults_to_home_dot_cairn(monkeypatch):
    # Arrange
    monkeypatch.delenv(system.CAIRN_HOME_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/tester")))

    # Act / Assert
    assert system.default_vault_root() == Path("/Users/tester/.cairn")


def test_vault_root_uses_pointer_file_when_no_env(monkeypatch, tmp_path):
    # Arrange: no CAIRN_HOME, a pointer file under a fake home
    monkeypatch.delenv(system.CAIRN_HOME_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    system.set_vault_location(Path("/Volumes/share/cairn"))

    # Act / Assert: the pointer location is used
    assert system.default_vault_root() == Path("/Volumes/share/cairn")


def test_env_wins_over_pointer_file(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    system.set_vault_location(Path("/Volumes/share/cairn"))
    monkeypatch.setenv(system.CAIRN_HOME_ENV, "/env/vault")

    assert system.default_vault_root() == Path("/env/vault")


def test_set_vault_location_writes_pointer_and_expands(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    resolved = system.set_vault_location(Path("~/net-vault"))

    assert resolved == Path("~/net-vault").expanduser()
    pointer = tmp_path / ".config" / "cairn" / "location"
    assert pointer.read_text().strip() == str(Path("~/net-vault").expanduser())


def test_machine_name_strips_domain(monkeypatch):
    monkeypatch.setattr(system.socket, "gethostname", lambda: "mac-mini.local")
    assert system.default_machine_name() == "mac-mini"


def test_machine_name_falls_back_when_empty(monkeypatch):
    monkeypatch.setattr(system.socket, "gethostname", lambda: "")
    assert system.default_machine_name() == "cairn"


def test_machine_override_reads_env(monkeypatch):
    # Arrange
    monkeypatch.setenv(system.CAIRN_MACHINE_ENV, "sessionA")

    # Act / Assert: the exact exported identity is returned
    assert system.machine_name_override() == "sessionA"


def test_machine_override_strips_surrounding_whitespace(monkeypatch):
    monkeypatch.setenv(system.CAIRN_MACHINE_ENV, "  sessionB  ")
    assert system.machine_name_override() == "sessionB"


def test_machine_override_none_when_unset(monkeypatch):
    monkeypatch.delenv(system.CAIRN_MACHINE_ENV, raising=False)
    assert system.machine_name_override() is None


def test_machine_override_blank_treated_as_unset(monkeypatch):
    # An exported-but-empty variable must not become an invalid "" identity.
    monkeypatch.setenv(system.CAIRN_MACHINE_ENV, "   ")
    assert system.machine_name_override() is None
