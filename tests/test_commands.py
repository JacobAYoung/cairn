"""CLI-level integration tests: drive real commands through :func:`cairn.cli.main`.

Commands are constructed with injected ``vault_root`` / ``cwd`` / ``now`` so they operate on a
temp vault + project, then dispatched exactly as the CLI would. Asserts both the printed output
and the on-disk effect, plus that a bad profile flows through the CairnError boundary to exit 1.
"""

from __future__ import annotations

import pytest

from cairn.cli import main
from cairn.commands import (
    ClearCommand,
    ImportCommand,
    LsCommand,
    StatusCommand,
    UseCommand,
)


@pytest.fixture
def env(tmp_path):
    """A seeded temp vault + empty project, and a factory for injected commands."""
    vault_root = tmp_path / "vault"
    for skill in ("develop", "audit"):
        (vault_root / "skills" / skill).mkdir(parents=True)
    (vault_root / "memories").mkdir(parents=True)
    (vault_root / "memories" / "code-conventions.md").write_text("conv")
    (vault_root / "profiles.toml").write_text(
        """
        [profiles.dev-heavy]
        skills   = ["develop", "audit"]
        memories = ["code-conventions"]
        model    = "opus"
        """
    )
    project = tmp_path / "proj"
    project.mkdir()

    def make(cmd_cls):
        return cmd_cls(vault_root=lambda: vault_root, cwd=lambda: project, now=lambda: "T0")

    return {"vault_root": vault_root, "project": project, "make": make}


def test_use_activates_and_reports(env, capsys):
    # Act
    code = main(["use", "dev-heavy"], commands=[env["make"](UseCommand)])

    # Assert OUTPUT + exit code
    assert code == 0
    out = capsys.readouterr().out
    assert "Activated dev-heavy" in out
    assert "model:    opus" in out
    # Assert STATE: the skill symlink exists in the project
    assert (env["project"] / ".claude" / "skills" / "develop").is_symlink()


def test_use_unknown_profile_exits_one_via_error_boundary(env, capsys):
    # Act
    code = main(["use", "ghost"], commands=[env["make"](UseCommand)])

    # Assert: CairnError -> exit 1 + stderr message, and nothing was created
    assert code == 1
    assert "unknown profile" in capsys.readouterr().err
    assert not (env["project"] / ".claude").exists()


def test_clear_reverses_activation(env, capsys):
    use, clear = env["make"](UseCommand), env["make"](ClearCommand)
    main(["use", "dev-heavy"], commands=[use])

    # Act
    code = main(["clear"], commands=[clear])

    # Assert
    assert code == 0
    assert "Cleared dev-heavy" in capsys.readouterr().out
    assert not (env["project"] / ".claude" / "skills" / "develop").exists()


def test_status_shows_active_profile(env, capsys):
    main(["use", "dev-heavy"], commands=[env["make"](UseCommand)])
    capsys.readouterr()  # discard use output

    # Act
    main(["status"], commands=[env["make"](StatusCommand)])

    # Assert
    out = capsys.readouterr().out
    assert "active:   dev-heavy" in out
    assert "sync:     off" in out


def test_ls_lists_inventory(env, capsys):
    main(["ls"], commands=[env["make"](LsCommand)])
    out = capsys.readouterr().out
    assert "skills:   audit, develop" in out
    assert "memories: code-conventions" in out
    assert "profiles: dev-heavy" in out


def test_import_seeds_vault_from_source(env, capsys, tmp_path):
    # Arrange: a source skills dir with a new skill not yet in the vault
    src = tmp_path / "src-skills"
    (src / "web-notes").mkdir(parents=True)
    (src / "web-notes" / "SKILL.md").write_text("x")

    # Act
    code = main(["import", "--skills", str(src)], commands=[env["make"](ImportCommand)])

    # Assert
    assert code == 0
    assert "Imported 1 skill" in capsys.readouterr().out
    assert (env["vault_root"] / "skills" / "web-notes" / "SKILL.md").read_text() == "x"
