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
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from cairn.activation import activate, deactivate, read_state, resolve_bundle
from cairn.config import load_cairn_config, load_profiles
from cairn.importer import import_into_vault
from cairn.sync import make_sync_backend
from cairn.system import default_machine_name, default_vault_root
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

    def run(self, args: argparse.Namespace) -> int:
        vault = self.vault()
        profiles = load_profiles(vault.profiles_path)
        names = [n.strip() for n in args.profiles.split(",") if n.strip()]
        bundle = resolve_bundle(profiles, names)
        result = activate(self._cwd(), vault, bundle, now=self._now())
        print(f"Activated {', '.join(result.profiles)} in {self._cwd()}")
        print(f"  skills:   {', '.join(result.linked_skills) or '(none)'}")
        print(f"  memories: {', '.join(result.linked_memories) or '(none)'}")
        print(f"  model:    {result.model or '(unchanged)'}")
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
        config = load_cairn_config(
            vault.cairn_config_path, default_machine_name=default_machine_name()
        )
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


def all_commands() -> list:
    """The registered command set, in help-display order."""
    return [
        ImportCommand(),
        UseCommand(),
        ClearCommand(),
        StatusCommand(),
        LsCommand(),
    ]
