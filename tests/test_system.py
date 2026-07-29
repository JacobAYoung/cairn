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


def test_machine_name_strips_domain(monkeypatch):
    monkeypatch.setattr(system.socket, "gethostname", lambda: "mac-mini.local")
    assert system.default_machine_name() == "mac-mini"


def test_machine_name_falls_back_when_empty(monkeypatch):
    monkeypatch.setattr(system.socket, "gethostname", lambda: "")
    assert system.default_machine_name() == "cairn"
