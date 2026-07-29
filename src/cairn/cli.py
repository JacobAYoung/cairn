"""Cairn's command-line entry point.

This module is a thin *dispatch* layer and nothing more: it parses ``argv``, routes to a
registered command handler, and returns a process exit code. Command implementations live
in their own modules and expose a :class:`Command`; they register in :data:`COMMANDS`. Adding
a command is therefore one new entry, never an edit to a growing ``if/elif`` here — the seam
that keeps this file from turning into a god-function as the tool grows.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from cairn import __version__
from cairn.errors import CairnError


@runtime_checkable
class Command(Protocol):
    """One CLI subcommand.

    A command owns its own argument registration (:meth:`configure`) and its behavior
    (:meth:`run`). Keeping both on the command object — rather than in a central parser
    builder — is what lets a new command be added without touching this module's logic.
    """

    name: str
    help: str

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Register this command's arguments on its subparser."""
        ...

    def run(self, args: argparse.Namespace) -> int:
        """Execute the command; return the process exit code (0 = success)."""
        ...


def _registered_commands() -> list[Command]:
    """The production command set. Imported lazily to keep ``build_parser`` importable cheaply."""
    from cairn.commands import all_commands

    return all_commands()


def build_parser(commands: Sequence[Command]) -> argparse.ArgumentParser:
    """Build the top-level argument parser, wiring each command onto its own subparser.

    Injecting ``commands`` (rather than reading the module global) keeps this pure and
    lets tests build a parser over fake commands.
    """
    parser = argparse.ArgumentParser(
        prog="cairn",
        description="Portable, toggleable, cross-machine vault for your Claude Code setup.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cairn {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for command in commands:
        subparser = subparsers.add_parser(command.name, help=command.help)
        command.configure(subparser)
        # Stash the handler on the namespace so main() can dispatch without a lookup table.
        subparser.set_defaults(_handler=command.run)
    return parser


def main(argv: Sequence[str] | None = None, commands: Sequence[Command] | None = None) -> int:
    """Parse ``argv`` and dispatch to the selected command.

    Returns the command's exit code, or 0 after printing help when no command is given.
    ``commands`` is injectable so tests can dispatch over fakes; production uses the registered
    set. Any :class:`~cairn.errors.CairnError` a command raises is caught here and turned into a
    clean ``stderr`` message + exit code 1 — commands never print-and-exit themselves.
    """
    resolved = list(_registered_commands() if commands is None else commands)
    parser = build_parser(resolved)
    args = parser.parse_args(argv)

    handler = getattr(args, "_handler", None)
    if handler is None:
        # No subcommand supplied — show help rather than failing silently.
        parser.print_help()
        return 0
    try:
        return handler(args)
    except CairnError as exc:
        print(f"cairn: error: {exc}", file=sys.stderr)
        return 1
