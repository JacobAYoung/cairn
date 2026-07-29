"""CLI-level integration tests: drive real commands through :func:`cairn.cli.main`.

Commands are constructed with injected ``vault_root`` / ``cwd`` / ``now`` so they operate on a
temp vault + project, then dispatched exactly as the CLI would. Asserts both the printed output
and the on-disk effect, plus that a bad profile flows through the CairnError boundary to exit 1.
"""

from __future__ import annotations

import json

import pytest

from cairn.cli import main
from cairn.commands import (
    AskCommand,
    BriefCommand,
    CheckpointCommand,
    ClearCommand,
    ImportCommand,
    InboxCommand,
    InitCommand,
    LsCommand,
    SendCommand,
    SessionStartCommand,
    StatusCommand,
    SyncMemoryCommand,
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
    (vault_root / "cairn.toml").write_text(
        """
        [machine]
        name = "testbox"

        [delegate]
        enabled = true
        default = "qwen2.5:14b"
        tasks = { summarize = "qwen-sum" }
        """
    )
    project = tmp_path / "proj"
    project.mkdir()

    def make(cmd_cls, **extra):
        return cmd_cls(
            vault_root=lambda: vault_root, cwd=lambda: project, now=lambda: "T0", **extra
        )

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


def test_ask_prints_local_model_output(env, capsys):
    # Arrange: inject a fake POST so no live Ollama is needed
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return {"response": "3-line summary"}

    ask = env["make"](AskCommand, post=fake_post)

    # Act
    code = main(["ask", "summarize", "big blob"], commands=[ask])

    # Assert: prints model output; routed to the task's mapped model
    assert code == 0
    assert capsys.readouterr().out.strip() == "3-line summary"
    assert calls[0][1]["model"] == "qwen-sum"


def test_checkpoint_then_brief_roundtrip(env, capsys):
    # Act: save a checkpoint, then read it back
    main(["checkpoint", "-m", "decided to use TOML"], commands=[env["make"](CheckpointCommand)])
    capsys.readouterr()
    main(["brief"], commands=[env["make"](BriefCommand)])

    # Assert: brief shows the note, stamped for this machine
    out = capsys.readouterr().out
    assert "decided to use TOML" in out
    assert "— testbox" in out
    # And it landed in the vault under the project key
    assert (env["vault_root"] / "session-notes" / "proj.md").exists()


def test_sync_memory_enable_then_off(env, capsys):
    # Enable
    main(["sync-memory"], commands=[env["make"](SyncMemoryCommand)])
    settings_path = env["project"] / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text())
    assert settings["autoMemoryDirectory"] == str(env["vault_root"] / "auto-memory" / "proj")

    # Disable
    capsys.readouterr()
    main(["sync-memory", "--off"], commands=[env["make"](SyncMemoryCommand)])
    assert "autoMemoryDirectory" not in json.loads(settings_path.read_text())


def test_send_then_inbox_roundtrip(env, capsys):
    # Send to this same machine (testbox) so inbox picks it up
    main(["send", "testbox", "ping from me"], commands=[env["make"](SendCommand)])
    capsys.readouterr()

    # Act
    main(["inbox"], commands=[env["make"](InboxCommand)])

    # Assert
    out = capsys.readouterr().out
    assert "ping from me" in out
    assert "from testbox" in out


def test_init_scaffolds_vault_and_wires_claude(env, capsys, tmp_path):
    # Arrange: a fresh vault root + temp Claude dir with an existing skill to import
    fresh_vault = tmp_path / "fresh-vault"
    claude_dir = tmp_path / "claude"
    (claude_dir / "skills" / "myskill").mkdir(parents=True)
    (claude_dir / "skills" / "myskill" / "SKILL.md").write_text("x")

    init = InitCommand(vault_root=lambda: fresh_vault, cwd=lambda: env["project"], now=lambda: "T0")

    # Act
    code = main(
        ["init", "--claude-dir", str(claude_dir), "--sync", "folder"], commands=[init]
    )

    # Assert: config scaffolded, existing skill imported, cairn skill + hook installed
    assert code == 0
    assert (fresh_vault / "cairn.toml").exists()
    assert (fresh_vault / "profiles.toml").exists()
    assert (fresh_vault / "skills" / "myskill").is_dir()  # imported
    assert (claude_dir / "skills" / "cairn" / "SKILL.md").exists()  # bundled skill installed
    settings = json.loads((claude_dir / "settings.json").read_text())
    hooks = settings["hooks"]["SessionStart"][0]["hooks"]
    assert hooks[0]["command"] == "cairn session-start"


def test_session_start_emits_json_for_active_profile(env, capsys):
    main(["use", "dev-heavy"], commands=[env["make"](UseCommand)])
    capsys.readouterr()

    # Act
    main(["session-start"], commands=[env["make"](SessionStartCommand)])

    # Assert: valid JSON naming the active profile + reloadSkills
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["reloadSkills"] is True
    assert "dev-heavy" in payload["hookSpecificOutput"]["additionalContext"]


def test_session_start_emits_empty_json_when_nothing_active(env, capsys):
    # No profile active, no default configured in the fixture, no checkpoint
    main(["session-start"], commands=[env["make"](SessionStartCommand)])
    assert json.loads(capsys.readouterr().out) == {}


def test_init_vault_path_relocates_vault_and_remembers_it(env, capsys, tmp_path, monkeypatch):
    # Arrange: fake home so the pointer file doesn't touch the real ~/.config
    from pathlib import Path

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    (tmp_path / "home").mkdir()
    net_vault = tmp_path / "netdrive" / "cairn"
    claude_dir = tmp_path / "claude"

    init = InitCommand(vault_root=lambda: tmp_path / "unused", cwd=lambda: env["project"])

    # Act: point the vault at the "network drive"
    code = main(
        ["init", "--vault-path", str(net_vault), "--claude-dir", str(claude_dir)],
        commands=[init],
    )

    # Assert: vault scaffolded at the network path, and the location is remembered
    assert code == 0
    assert (net_vault / "cairn.toml").exists()
    pointer = tmp_path / "home" / ".config" / "cairn" / "location"
    assert pointer.read_text().strip() == str(net_vault)
