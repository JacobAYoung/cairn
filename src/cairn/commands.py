"""CLI subcommands — the composition root that wires pure logic to the real environment.

Each command is a small class implementing :class:`cairn.cli.Command`. ``run`` is where the
impure wiring lives: locate the vault, load config/profiles, call the logic layer
(:mod:`cairn.activation`, :mod:`cairn.importer`, ...), and print a result. The logic stays pure
and unit-tested; these classes are thin glue tested at the CLI level.

Dependencies (vault root, cwd, clock) are injected via the constructor with real defaults, so a
test can drive a command against a temp vault/project without monkeypatching globals.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from cairn import sessions
from cairn.activation import activate, deactivate, read_state, resolve_bundle
from cairn.automemory import disable as auto_disable
from cairn.automemory import enable as auto_enable
from cairn.bundle import export_bundle, install_bundle
from cairn.checkpoints import latest_brief, write_checkpoint
from cairn.claude_setup import install_session_start_hook, install_skill
from cairn.config import CairnConfig, load_cairn_config, load_profiles
from cairn.delegate import Delegator
from cairn.doctor import FAIL, run_checks
from cairn.errors import CairnError
from cairn.handoff import build_handoff_payload, latest_handoff
from cairn.importer import import_into_vault
from cairn.index import search as index_search
from cairn.mailbox import inbox as read_inbox
from cairn.mailbox import mark_read, wait_for_inbox
from cairn.mailbox import send as send_message
from cairn.scaffold import write_starter_config
from cairn.session_start import build_session_start_output
from cairn.sync import make_sync_backend
from cairn.system import (
    default_machine_name,
    default_vault_root,
    machine_name_override,
    set_vault_location,
)
from cairn.vault import Vault


class _Base:
    """Shared wiring: resolve the vault root and current project once, injectably."""

    name = ""
    help = ""

    def __init__(
        self,
        *,
        vault_root: Callable[[], Path] = default_vault_root,
        cwd: Callable[[], Path] = Path.cwd,
        now: Callable[[], str] = lambda: datetime.now().isoformat(timespec="seconds"),
    ) -> None:
        self._vault_root = vault_root
        self._cwd = cwd
        self._now = now

    def vault(self) -> Vault:
        return Vault(self._vault_root())

    def config(self) -> CairnConfig:
        return load_cairn_config(
            self.vault().cairn_config_path,
            default_machine_name=default_machine_name(),
            machine_override=machine_name_override(),
        )

    def project_key(self) -> str:
        """Stable-enough key for this project: the working directory's name."""
        return self._cwd().name

    def stamp(self) -> str:
        """A filename-safe, sortable timestamp derived from ``now`` (e.g. 20260729T174522)."""
        return self._now().replace("-", "").replace(":", "")

    def configure(self, parser: argparse.ArgumentParser) -> None:  # default: no args
        return None


class ImportCommand(_Base):
    name = "import"
    help = "Seed the vault from an existing Claude Code setup (copies skills/memories)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--skills",
            type=Path,
            default=Path.home() / ".claude" / "skills",
            help="directory of skill folders to import (default: ~/.claude/skills)",
        )
        parser.add_argument(
            "--memories",
            type=Path,
            default=None,
            help="directory of memory .md files to import",
        )

    def run(self, args: argparse.Namespace) -> int:
        result = import_into_vault(
            self.vault(), skills_src=args.skills, memories_src=args.memories
        )
        print(
            f"Imported {len(result.skills_imported)} skill(s), "
            f"{len(result.memories_imported)} memory(ies); skipped {len(result.skipped)}."
        )
        for name in result.skills_imported:
            print(f"  + skill  {name}")
        for name in result.memories_imported:
            print(f"  + memory {name}")
        return 0


class UseCommand(_Base):
    name = "use"
    help = "Activate one or more profiles in the current project."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "profiles", help="comma-separated profile name(s), e.g. dev-heavy,research"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="show what would change (and validate the bundle) without touching anything",
        )

    def run(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        profiles = load_profiles(vault.profiles_path)
        names = [n.strip() for n in args.profiles.split(",") if n.strip()]
        bundle = resolve_bundle(profiles, names)

        if args.dry_run:
            # Validate everything exists (raises on a missing skill/memory) but change nothing.
            for skill in bundle.skills:
                vault.skill_path(skill)
            for memory in bundle.memories:
                vault.memory_path(memory)
            print(f"[dry-run] would activate {', '.join(bundle.profiles)} in {self._cwd()}")
            print(f"  skills:   {', '.join(bundle.skills) or '(none)'}")
            print(f"  memories: {', '.join(bundle.memories) or '(none)'}")
            print(f"  model:    {bundle.model or '(unchanged)'}")
            print(f"  mcp:      {', '.join(bundle.mcp) or '(none)'}")
            print("  nothing was changed.")
            return 0

        result = activate(self._cwd(), vault, bundle, now=self._now())
        print(f"Activated {', '.join(result.profiles)} in {self._cwd()}")
        print(f"  skills:   {', '.join(result.linked_skills) or '(none)'}")
        print(f"  memories: {', '.join(result.linked_memories) or '(none)'}")
        print(f"  model:    {result.model or '(unchanged)'}")
        print(f"  mcp:      {', '.join(result.mcp) or '(none)'}")
        print("  (takes effect on the next Claude Code session)")
        return 0


class ClearCommand(_Base):
    name = "clear"
    help = "Deactivate Cairn in the current project (reverse all changes)."

    def run(self, args: argparse.Namespace) -> int:
        profiles = deactivate(self._cwd())
        if profiles:
            print(f"Cleared {', '.join(profiles)} from {self._cwd()}")
        else:
            print("Nothing active here.")
        return 0


class StatusCommand(_Base):
    name = "status"
    help = "Show what's active in this project and the vault/sync summary."

    def run(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        config = self.config()
        state = read_state(self._cwd())
        sync_status = make_sync_backend(config.sync.mode, vault.root).status()

        print(f"machine:  {config.machine.name}")
        print(f"vault:    {vault.root}" + ("" if vault.exists() else "  (not created yet)"))
        print(f"sync:     {sync_status.mode} — {sync_status.detail}")
        if state:
            print(f"active:   {', '.join(state['profiles'])}  (since {state['activated_at']})")
        else:
            print("active:   (none)")
        return 0


class LsCommand(_Base):
    name = "ls"
    help = "List skills, memories, and profiles in the vault."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "what",
            nargs="?",
            choices=("skills", "memories", "profiles", "all"),
            default="all",
        )

    def run(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        if args.what in ("skills", "all"):
            print("skills:   " + (", ".join(vault.list_skills()) or "(none)"))
        if args.what in ("memories", "all"):
            print("memories: " + (", ".join(vault.list_memories()) or "(none)"))
        if args.what in ("profiles", "all"):
            profiles = load_profiles(vault.profiles_path)
            print("profiles: " + (", ".join(sorted(profiles)) or "(none)"))
        return 0


class AskCommand(_Base):
    name = "ask"
    help = "Delegate a bulk/mechanical subtask to a local model (free tokens)."

    def __init__(self, *, post=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._post = post  # injectable HTTP POST for tests; None -> Delegator's real default

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("task", help="task type mapped via [delegate].tasks (e.g. summarize)")
        parser.add_argument("prompt", help="the prompt text")

    def run(self, args: argparse.Namespace) -> int:
        extra = {"post": self._post} if self._post is not None else {}
        result = Delegator(self.config().delegate, **extra).ask(args.task, args.prompt)
        print(result.text)
        return 0


class CheckpointCommand(_Base):
    name = "checkpoint"
    help = "Save a warm-start note for this project (from --message or stdin)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-m", "--message", default=None, help="the brief; if omitted, read from stdin"
        )

    def run(self, args: argparse.Namespace) -> int:
        text = (args.message if args.message is not None else sys.stdin.read()).strip()
        if not text:
            raise CairnError("nothing to checkpoint (empty message)")
        cfg = self.config()
        path = write_checkpoint(
            self.vault(), self.project_key(), text, machine=cfg.machine.name, now=self._now()
        )
        print(f"Checkpoint saved for {self.project_key()} -> {path}")
        return 0


class BriefCommand(_Base):
    name = "brief"
    help = "Print the latest warm-start note for this project."

    def run(self, args: argparse.Namespace) -> int:
        brief = latest_brief(self.vault(), self.project_key())
        print(brief if brief else "(no checkpoint for this project yet)")
        return 0


class RecallCommand(_Base):
    name = "recall"
    help = "Full-text search across your memories and warm-start notes."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("query", help="search text")
        parser.add_argument("--limit", type=int, default=10, help="max results (default 10)")

    def run(self, args: argparse.Namespace) -> int:
        hits = index_search(self.vault(), args.query, limit=args.limit)
        if not hits:
            print("No matches.")
            return 0
        for hit in hits:
            print(f"[{hit.kind}] {hit.name}: {hit.snippet}")
        return 0


class DoctorCommand(_Base):
    name = "doctor"
    help = "Diagnose vault / config / links / sync / delegate health."

    def __init__(self, *, ping=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ping = ping  # injectable reachability probe for tests

    def run(self, args: argparse.Namespace) -> int:
        extra = {"ping": self._ping} if self._ping is not None else {}
        checks = run_checks(self.vault(), self._cwd(), **extra)
        symbol = {"ok": "✓", "warn": "!", "fail": "✗"}
        for check in checks:
            print(f"  {symbol.get(check.status, '?')} {check.name}: {check.detail}")
        failures = [c for c in checks if c.status == FAIL]
        if failures:
            print(f"\n{len(failures)} problem(s) found.")
            return 1
        return 0


class SyncMemoryCommand(_Base):
    name = "sync-memory"
    help = "Redirect Claude's auto-memory to the synced vault (or --off to undo)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--off", action="store_true", help="stop syncing auto-memory for this project"
        )

    def run(self, args: argparse.Namespace) -> int:
        if args.off:
            removed = auto_disable(self._cwd())
            print("Auto-memory sync disabled." if removed else "Auto-memory sync was not enabled.")
            return 0
        target = auto_enable(self.vault(), self._cwd(), self.project_key())
        print(f"Auto-memory for {self.project_key()} -> {target}")
        print("  (takes effect on the next Claude Code session)")
        return 0


class SendCommand(_Base):
    name = "send"
    help = "Send a message to another machine's mailbox (Tier-0, no ports)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("machine", help="recipient machine name")
        parser.add_argument("message", help="the message text")

    def run(self, args: argparse.Namespace) -> int:
        vault, cfg = self.vault(), self.config()
        path = send_message(
            vault, args.machine, args.message, from_machine=cfg.machine.name, stamp=self.stamp()
        )
        make_sync_backend(cfg.sync.mode, vault.root).push(f"cairn: message to {args.machine}")
        print(f"Sent to {args.machine}: {path.name}")
        return 0


class HandoffCommand(_Base):
    name = "handoff"
    help = "Package this project's active profile + latest brief and send it to another machine."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("machine", help="recipient machine name")
        parser.add_argument("-m", "--message", default=None, help="optional note to include")

    def run(self, args: argparse.Namespace) -> int:
        vault, cfg = self.vault(), self.config()
        state = read_state(self._cwd())
        profiles = list(state["profiles"]) if state else []
        brief = latest_brief(vault, self.project_key())
        payload = build_handoff_payload(self.project_key(), profiles, args.message, brief)
        send_message(
            vault, args.machine, payload, from_machine=cfg.machine.name, stamp=self.stamp()
        )
        make_sync_backend(cfg.sync.mode, vault.root).push(f"cairn: handoff to {args.machine}")
        names = ", ".join(profiles) or "none"
        print(f"Handed off {self.project_key()} to {args.machine} (profiles: {names}).")
        return 0


class ResumeCommand(_Base):
    name = "resume"
    help = "Show the latest handoff sent to this machine."

    def run(self, args: argparse.Namespace) -> int:
        vault, cfg = self.vault(), self.config()
        make_sync_backend(cfg.sync.mode, vault.root).pull()
        handoff = latest_handoff(read_inbox(vault, cfg.machine.name))
        if handoff is None:
            print("No handoff waiting.")
            return 0
        print(f"— handoff from {handoff.sender}\n{handoff.body}")
        return 0


class InboxCommand(_Base):
    name = "inbox"
    help = "Read messages sent to this machine (Tier-0)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--read", action="store_true", help="mark messages read after showing them"
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            help="block until a message arrives (turns inbox into a receive), then show it",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=None,
            metavar="SECONDS",
            help="with --wait, give up after this many seconds (default: wait forever)",
        )

    def run(self, args: argparse.Namespace) -> int:
        vault, cfg = self.vault(), self.config()
        backend = make_sync_backend(cfg.sync.mode, vault.root)
        if args.wait:
            messages = wait_for_inbox(
                vault,
                cfg.machine.name,
                now_fn=time.monotonic,
                sleep_fn=time.sleep,
                poll_fn=backend.pull,
                timeout=args.timeout,
            )
        else:
            backend.pull()
            messages = read_inbox(vault, cfg.machine.name)
        if not messages:
            timed_out = args.wait and args.timeout is not None
            waited = f" (waited {args.timeout:g}s)" if timed_out else ""
            print(f"Inbox empty{waited}.")
            return 0
        for message in messages:
            print(f"— from {message.sender} ({message.filename})\n{message.body}\n")
        if args.read:
            print(f"Marked {mark_read(vault, cfg.machine.name)} message(s) read.")
        return 0


def _format_age(seconds: float) -> str:
    """Human-readable elapsed time for roster listings (e.g. ``12s``, ``5m``, ``2h``, ``3d``)."""
    seconds = int(max(seconds, 0))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


class BroadcastCommand(_Base):
    name = "broadcast"
    help = "Send a message to every other session on this machine (same-PC fan-out)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("message", help="the message text")
        parser.add_argument(
            "--include-self",
            action="store_true",
            help="also deliver a copy to your own inbox",
        )

    def run(self, args: argparse.Namespace) -> int:
        vault, cfg = self.vault(), self.config()
        me, host = cfg.machine.name, default_machine_name()
        peers = [
            record.name
            for record in sessions.roster(vault, host=host)
            if args.include_self or record.name != me
        ]
        if not peers:
            print(
                "No other sessions registered on this machine. "
                "Have each session run: cairn session start <name>"
            )
            return 0
        for peer in peers:
            send_message(vault, peer, args.message, from_machine=me, stamp=self.stamp())
        make_sync_backend(cfg.sync.mode, vault.root).push(
            f"cairn: broadcast to {len(peers)} session(s)"
        )
        print(f"Broadcast to {len(peers)} session(s): {', '.join(peers)}")
        return 0


class SessionCommand(_Base):
    name = "session"
    help = "Manage this machine's session roster (identity + presence for same-PC messaging)."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action", metavar="<action>", required=True)
        start = sub.add_parser(
            "start", help="register/refresh a session identity; prints its export line"
        )
        start.add_argument("name", nargs="?", help="session name (default: current $CAIRN_MACHINE)")
        sub.add_parser("ls", help="list this machine's sessions with presence (live/stale)")
        sub.add_parser("whoami", help="show this shell's effective session identity and its source")
        stop = sub.add_parser("end", help="remove a session from the roster")
        stop.add_argument("name", nargs="?", help="session name (default: current $CAIRN_MACHINE)")
        sub.add_parser("prune", help="drop sessions not seen within the staleness window")

    def _resolve_name(self, explicit: str | None) -> str:
        """The session name to act on: an explicit CLI arg, else this shell's $CAIRN_MACHINE.

        Raises :class:`CairnError` when neither is available, so the user gets an actionable
        message instead of silently registering the hostname as a "session".
        """
        name = explicit or machine_name_override()
        if not name:
            raise CairnError(
                "no session name: pass one (cairn session start <name>) or export CAIRN_MACHINE"
            )
        return name

    def run(self, args: argparse.Namespace) -> int:
        dispatch = {
            "start": self._start,
            "ls": self._ls,
            "whoami": self._whoami,
            "end": self._end,
            "prune": self._prune,
        }
        return dispatch[args.action](args)

    def _start(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        name = self._resolve_name(args.name)
        sessions.register(
            vault, name, host=default_machine_name(), project=self.project_key(), now=self._now()
        )
        print(f"Registered session '{name}' on {default_machine_name()}.")
        if machine_name_override() != name:
            print("This shell is not yet that session. To become it, run:")
            print(f"  export CAIRN_MACHINE={name}")
        return 0

    def _ls(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        host, now = default_machine_name(), self._now()
        records = sessions.roster(vault, host=host)
        if not records:
            print(f"No sessions registered on {host}. Start one: cairn session start <name>")
            return 0
        me = machine_name_override()
        print(f"sessions on {host}:")
        for record in records:
            live = sessions.is_live(record, now=now)
            marker = "●" if live else "○"
            age = _format_age(sessions.seconds_between(record.last_seen_utc, now))
            suffix = "" if live else " (stale)"
            you = "  <- you" if record.name == me else ""
            print(
                f"  {marker} {record.name}   project={record.project}   "
                f"seen {age} ago{suffix}{you}"
            )
        return 0

    def _whoami(self, args: argparse.Namespace) -> int:
        override = machine_name_override()
        identity = self.config().machine.name
        source = "$CAIRN_MACHINE" if override else "cairn.toml [machine].name / hostname"
        print(f"identity: {identity}")
        print(f"source:   {source}")
        if override is None:
            print("tip: export CAIRN_MACHINE=<name> to give this session its own mailbox")
        return 0

    def _end(self, args: argparse.Namespace) -> int:
        name = self._resolve_name(args.name)
        removed = sessions.end(self.vault(), name)
        print(f"Removed session '{name}'." if removed else f"No session '{name}' in the roster.")
        return 0

    def _prune(self, args: argparse.Namespace) -> int:
        removed = sessions.prune(self.vault(), now=self._now(), host=default_machine_name())
        detail = f": {', '.join(removed)}" if removed else "."
        print(f"Pruned {len(removed)} stale session(s){detail}")
        return 0


def _git_clone(url: str, dest: Path) -> None:
    """Shallow-clone ``url`` into ``dest``; raise CairnError on failure."""
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise CairnError(f"git clone failed: {result.stderr.strip() or url}")


class ExportCommand(_Base):
    name = "export"
    help = "Package a profile (+ its skills/memories) into a shareable bundle directory."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("profile", help="profile to export")
        parser.add_argument("dest", type=Path, help="directory to write the bundle into")

    def run(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        profiles = load_profiles(vault.profiles_path)
        result = export_bundle(vault, profiles, args.profile, args.dest)
        print(f"Exported '{result.profile}' -> {result.dest}")
        print(f"  skills:   {', '.join(result.skills) or '(none)'}")
        print(f"  memories: {', '.join(result.memories) or '(none)'}")
        print("Push that directory to GitHub; others run `cairn install <url>`.")
        return 0


class InstallCommand(_Base):
    name = "install"
    help = "Install a shared bundle from a git URL or local directory into your vault."

    def __init__(self, *, cloner=_git_clone, **kwargs) -> None:
        super().__init__(**kwargs)
        self._clone = cloner  # injectable so the URL path is testable without network

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("source", help="git URL (e.g. GitHub) or a local bundle directory")

    def run(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        local = Path(args.source).expanduser()
        if local.is_dir():
            result = install_bundle(vault, local)
        else:
            tmp = Path(tempfile.mkdtemp(prefix="cairn-install-"))
            try:
                self._clone(args.source, tmp / "bundle")
                result = install_bundle(vault, tmp / "bundle")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        print(
            f"Installed: {len(result.profiles_added)} profile(s), "
            f"{len(result.skills_added)} skill(s), {len(result.memories_added)} memory(ies); "
            f"skipped {len(result.skipped)}."
        )
        for pname in result.profiles_added:
            print(f"  + profile {pname}")
        return 0


class InitCommand(_Base):
    name = "init"
    help = "One-time setup: scaffold the vault, import existing skills/memories, wire Claude."

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--claude-dir",
            type=Path,
            default=Path.home() / ".claude",
            help="Claude Code config dir to wire (default: ~/.claude)",
        )
        parser.add_argument(
            "--sync", default="off", help="sync mode for the starter config (default: off)"
        )
        parser.add_argument(
            "--vault-path",
            type=Path,
            default=None,
            help="put the vault here (e.g. a network drive or git checkout) and remember it",
        )
        parser.add_argument(
            "--skills",
            type=Path,
            default=None,
            help="skills dir to import (default: <claude-dir>/skills)",
        )
        parser.add_argument("--memories", type=Path, default=None, help="memories dir to import")

    def run(self, args: argparse.Namespace) -> int:
        # --vault-path relocates the vault (and remembers it) before anything is scaffolded.
        vault = Vault(set_vault_location(args.vault_path)) if args.vault_path else self.vault()
        claude_dir = args.claude_dir
        skills_src = args.skills if args.skills is not None else claude_dir / "skills"

        created = write_starter_config(
            vault, machine=default_machine_name(), sync_mode=args.sync
        )
        imported = import_into_vault(vault, skills_src=skills_src, memories_src=args.memories)
        skill_dest = install_skill(claude_dir / "skills")
        hook_added = install_session_start_hook(claude_dir / "settings.json")

        print(f"Cairn initialized at {vault.root}")
        print(f"  config:    {', '.join(created) or 'already present'}")
        print(
            f"  imported:  {len(imported.skills_imported)} skill(s), "
            f"{len(imported.memories_imported)} memory(ies)"
        )
        print(f"  skill:     installed -> {skill_dest}")
        print(f"  hook:      {'installed' if hook_added else 'already present'} (SessionStart)")
        print("\nNext: edit the `default` profile in profiles.toml, then start a Claude session.")
        return 0


class SessionStartCommand(_Base):
    name = "session-start"
    help = "(internal) SessionStart hook target — emits JSON for Claude Code."

    def run(self, args: argparse.Namespace) -> int:
        # A hook must NEVER break the session: swallow everything and emit empty JSON on failure.
        try:
            vault = self.vault()
            project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", str(self._cwd())))
            config = load_cairn_config(
                vault.cairn_config_path, default_machine_name=default_machine_name()
            )
            profiles = load_profiles(vault.profiles_path)
            output = build_session_start_output(
                vault, project_dir, config, profiles, now=self._now()
            )
        except Exception:
            output = {}
        print(json.dumps(output))
        return 0


def all_commands() -> list:
    """The registered command set, in help-display order."""
    return [
        InitCommand(),
        ImportCommand(),
        ExportCommand(),
        InstallCommand(),
        UseCommand(),
        ClearCommand(),
        StatusCommand(),
        LsCommand(),
        DoctorCommand(),
        AskCommand(),
        CheckpointCommand(),
        BriefCommand(),
        RecallCommand(),
        SyncMemoryCommand(),
        SendCommand(),
        InboxCommand(),
        BroadcastCommand(),
        SessionCommand(),
        HandoffCommand(),
        ResumeCommand(),
        SessionStartCommand(),
    ]
