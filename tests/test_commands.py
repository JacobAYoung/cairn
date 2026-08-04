"""CLI-level integration tests: drive real commands through :func:`cairn.cli.main`.

Commands are constructed with injected ``vault_root`` / ``cwd`` / ``now`` so they operate on a
temp vault + project, then dispatched exactly as the CLI would. Asserts both the printed output
and the on-disk effect, plus that a bad profile flows through the CairnError boundary to exit 1.
"""

from __future__ import annotations

import json

import pytest

from cairn import sessions
from cairn.cli import main
from cairn.commands import (
    AskCommand,
    BriefCommand,
    BroadcastCommand,
    CheckpointCommand,
    ClearCommand,
    DoctorCommand,
    ExportCommand,
    HandoffCommand,
    ImportCommand,
    InboxCommand,
    InitCommand,
    InstallCommand,
    LsCommand,
    RecallCommand,
    ResumeCommand,
    SendCommand,
    SessionCommand,
    SessionStartCommand,
    StatusCommand,
    SyncMemoryCommand,
    UseCommand,
    WorkersCommand,
)
from cairn.system import default_machine_name
from cairn.vault import Vault


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

        [[worker]]
        name = "delegate"
        backend = "claude"
        model = "sonnet"
        role = "search and summarize"

        [[worker]]
        name = "sum"
        backend = "local"
        model = "qwen2.5:14b"
        endpoint = "http://localhost:11434"
        role = "summarize text"
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


def test_inbox_wait_returns_present_message_without_blocking(env, capsys):
    # A message is already waiting, so --wait must return it on the first check (no real sleep)
    main(["send", "testbox", "waiting for you"], commands=[env["make"](SendCommand)])
    capsys.readouterr()

    code = main(["inbox", "--wait"], commands=[env["make"](InboxCommand)])

    out = capsys.readouterr().out
    assert code == 0
    assert "waiting for you" in out


def test_inbox_wait_with_zero_timeout_reports_empty(env, capsys):
    # Empty box + --timeout 0 must return at once rather than hang
    code = main(["inbox", "--wait", "--timeout", "0"], commands=[env["make"](InboxCommand)])

    out = capsys.readouterr().out
    assert code == 0
    assert "Inbox empty (waited 0s)." in out


def test_handoff_then_resume_carries_profile_and_brief(env, capsys):
    # Arrange: active profile + a checkpoint to carry
    main(["use", "dev-heavy"], commands=[env["make"](UseCommand)])
    main(["checkpoint", "-m", "mid-refactor"], commands=[env["make"](CheckpointCommand)])
    capsys.readouterr()

    # Act: hand off to this same machine (testbox), then resume
    main(["handoff", "testbox", "-m", "continue here"], commands=[env["make"](HandoffCommand)])
    capsys.readouterr()
    main(["resume"], commands=[env["make"](ResumeCommand)])

    # Assert: resume surfaces the project, active profile, note, and brief
    out = capsys.readouterr().out
    assert "### CAIRN HANDOFF" in out
    assert "profiles: dev-heavy" in out
    assert "note: continue here" in out
    assert "mid-refactor" in out


def test_resume_reports_nothing_when_no_handoff(env, capsys):
    main(["resume"], commands=[env["make"](ResumeCommand)])
    assert "No handoff waiting." in capsys.readouterr().out


def test_export_then_install_via_cli(env, capsys, tmp_path):
    # Export dev-heavy from the fixture vault to a bundle dir
    bundle = tmp_path / "bundle"
    code = main(["export", "dev-heavy", str(bundle)], commands=[env["make"](ExportCommand)])
    assert code == 0
    assert (bundle / "cairn-bundle.json").exists()
    capsys.readouterr()

    # Install it into a *different* fresh vault via a local path
    dest_vault = tmp_path / "dest-vault"
    installer = InstallCommand(vault_root=lambda: dest_vault, cwd=lambda: env["project"])
    code = main(["install", str(bundle)], commands=[installer])

    assert code == 0
    assert "1 profile(s)" in capsys.readouterr().out
    assert (dest_vault / "skills" / "develop").is_dir()
    assert "dev-heavy" in (dest_vault / "profiles.toml").read_text()


def test_install_from_url_uses_injected_cloner(env, capsys, tmp_path):
    # Prepare a bundle that the fake cloner will "clone" (copy) into place
    bundle = tmp_path / "bundle"
    main(["export", "dev-heavy", str(bundle)], commands=[env["make"](ExportCommand)])
    capsys.readouterr()

    import shutil

    def fake_cloner(url, dest):
        assert url == "https://github.com/someone/cairn-dev-heavy"
        shutil.copytree(bundle, dest)

    dest_vault = tmp_path / "dest2"
    installer = InstallCommand(
        vault_root=lambda: dest_vault, cwd=lambda: env["project"], cloner=fake_cloner
    )
    code = main(
        ["install", "https://github.com/someone/cairn-dev-heavy"], commands=[installer]
    )

    assert code == 0
    assert (dest_vault / "profiles.toml").exists()
    assert "dev-heavy" in (dest_vault / "profiles.toml").read_text()


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
    # The seeded claude-backend workers are materialized as subagents
    agent = (claude_dir / "agents" / "cairn-delegate.md").read_text()
    assert "model: sonnet" in agent


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


def test_use_dry_run_reports_plan_without_changing_anything(env, capsys):
    code = main(["use", "dev-heavy", "--dry-run"], commands=[env["make"](UseCommand)])

    assert code == 0
    out = capsys.readouterr().out
    assert "[dry-run] would activate dev-heavy" in out
    assert "model:    opus" in out
    # nothing created
    assert not (env["project"] / ".claude").exists()
    assert not (env["project"] / ".cairn").exists()


def test_doctor_reports_and_exits_nonzero_on_problem(env, capsys):
    # dev-heavy links a vault skill, then we break the vault by removing it -> dangling link
    main(["use", "dev-heavy"], commands=[env["make"](UseCommand)])
    (env["vault_root"] / "skills" / "develop").rmdir()  # now the symlink dangles
    capsys.readouterr()

    doctor = env["make"](DoctorCommand, ping=lambda e: True)
    code = main(["doctor"], commands=[doctor])

    out = capsys.readouterr().out
    assert "links:" in out
    assert code == 1  # dangling link is a failure


def test_recall_searches_notes(env, capsys):
    # Seed a checkpoint, then find it
    main(
        ["checkpoint", "-m", "chose Postgres for the store"],
        commands=[env["make"](CheckpointCommand)],
    )
    capsys.readouterr()

    main(["recall", "postgres"], commands=[env["make"](RecallCommand)])

    out = capsys.readouterr().out
    assert "[note] proj" in out


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


# --- same-PC sessions: session roster + broadcast -------------------------------------------


def _session_cmd(env, cmd_cls, now="2026-07-30T10:00:00"):
    """A session/broadcast command over the temp vault with a *real* ISO clock (roster listings
    parse timestamps, so the fixture's ``T0`` sentinel won't do)."""
    return cmd_cls(
        vault_root=lambda: env["vault_root"], cwd=lambda: env["project"], now=lambda: now
    )


def test_session_whoami_reports_override_identity(env, capsys, monkeypatch):
    monkeypatch.setenv("CAIRN_MACHINE", "sessionA")

    code = main(["session", "whoami"], commands=[env["make"](SessionCommand)])

    out = capsys.readouterr().out
    assert code == 0
    assert "identity: sessionA" in out
    assert "source:   $CAIRN_MACHINE" in out


def test_session_start_registers_and_prints_export_hint(env, capsys, monkeypatch):
    # No CAIRN_MACHINE exported, so this shell isn't yet "sessionA" -> hint should appear
    monkeypatch.delenv("CAIRN_MACHINE", raising=False)

    code = main(
        ["session", "start", "sessionA"], commands=[_session_cmd(env, SessionCommand)]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "Registered session 'sessionA'" in out
    assert "export CAIRN_MACHINE=sessionA" in out
    # On-disk presence file created with the right identity/host
    record = json.loads((env["vault_root"] / "sessions" / "sessionA.json").read_text())
    assert record["name"] == "sessionA"
    assert record["host"] == default_machine_name()


def test_session_start_without_name_or_env_exits_one(env, capsys, monkeypatch):
    monkeypatch.delenv("CAIRN_MACHINE", raising=False)

    code = main(["session", "start"], commands=[_session_cmd(env, SessionCommand)])

    assert code == 1
    assert "no session name" in capsys.readouterr().err


def test_session_ls_marks_live_session(env, capsys, monkeypatch):
    monkeypatch.delenv("CAIRN_MACHINE", raising=False)
    main(
        ["session", "start", "sessionA"],
        commands=[_session_cmd(env, SessionCommand, now="2026-07-30T10:00:00")],
    )
    capsys.readouterr()

    # List 5 seconds later
    code = main(
        ["session", "ls"],
        commands=[_session_cmd(env, SessionCommand, now="2026-07-30T10:00:05")],
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "● sessionA" in out  # live marker
    assert "seen 5s ago" in out
    assert "project=proj" in out


def test_broadcast_fans_out_to_peers_except_self(env, capsys, monkeypatch):
    monkeypatch.setenv("CAIRN_MACHINE", "sessionA")
    host = default_machine_name()
    vault = env["vault_root"]
    # Seed three sessions on this host (including self, to prove self is excluded)
    for peer in ("sessionA", "sessionB", "sessionC"):
        sessions.register(Vault(vault), peer, host=host, project="p", now="2026-07-30T10:00:00")

    code = main(["broadcast", "hello all"], commands=[env["make"](BroadcastCommand)])

    out = capsys.readouterr().out
    assert code == 0
    assert "Broadcast to 2 session(s): sessionB, sessionC" in out
    # Messages landed for the two peers, never for the sender
    assert (vault / "mailbox" / "sessionB").is_dir()
    assert (vault / "mailbox" / "sessionC").is_dir()
    assert not (vault / "mailbox" / "sessionA").exists()


def test_broadcast_with_no_peers_prints_guidance(env, capsys, monkeypatch):
    monkeypatch.setenv("CAIRN_MACHINE", "solo")

    code = main(["broadcast", "anyone?"], commands=[env["make"](BroadcastCommand)])

    out = capsys.readouterr().out
    assert code == 0
    assert "No other sessions registered" in out
    assert not (env["vault_root"] / "mailbox").exists()


# --- delegation workers ---------------------------------------------------------------------


def test_workers_ls_lists_both_backends(env, capsys):
    code = main(["workers", "ls"], commands=[env["make"](WorkersCommand)])

    out = capsys.readouterr().out
    assert code == 0
    assert "delegate  [claude:sonnet]  -> Task subagent cairn-delegate" in out
    assert "sum  [local:qwen2.5:14b]  -> local http://localhost:11434" in out


def test_workers_sync_installs_claude_subagents(env, capsys, tmp_path):
    claude_dir = tmp_path / "claude"

    code = main(
        ["workers", "sync", "--claude-dir", str(claude_dir)],
        commands=[env["make"](WorkersCommand)],
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "Installed 1 worker subagent(s)" in out  # the local worker is skipped
    assert "model: sonnet" in (claude_dir / "agents" / "cairn-delegate.md").read_text()
    assert not (claude_dir / "agents" / "cairn-sum.md").exists()


def test_workers_run_executes_local_worker_over_injected_post(env, capsys):
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return {"response": "condensed"}

    code = main(
        ["workers", "run", "sum", "big blob of text"],
        commands=[env["make"](WorkersCommand, post=fake_post)],
    )

    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == "condensed"
    assert calls == [
        ("http://localhost:11434/api/generate",
         {"model": "qwen2.5:14b", "prompt": "big blob of text", "stream": False})
    ]


def test_workers_run_on_claude_worker_exits_one(env, capsys):
    code = main(["workers", "run", "delegate", "x"], commands=[env["make"](WorkersCommand)])

    assert code == 1
    assert "delegate to it via the Task tool" in capsys.readouterr().err


def test_workers_run_unknown_name_exits_one(env, capsys):
    code = main(["workers", "run", "ghost", "x"], commands=[env["make"](WorkersCommand)])

    assert code == 1
    assert "no worker named 'ghost'" in capsys.readouterr().err
