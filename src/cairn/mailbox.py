"""Tier-0 cross-machine mailbox (SPEC Appendix C).

Messaging with **no daemon, no ports, no admin** — just files in the synced vault. ``send`` drops
a timestamped file into ``mailbox/<to-machine>/``; the other machine's ``inbox`` lists them
newest-first. Two machines never collide: each writes a distinct filename (its own timestamp +
sender), which is why the inbox is a directory of files, not one appended file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cairn.vault import Vault


@dataclass(frozen=True)
class Message:
    """One received message: its filename, the sender it came from, and the body text."""

    filename: str
    sender: str
    body: str


def _box(vault: Vault, machine: str) -> Path:
    return vault.mailbox_dir / machine


def send(vault: Vault, to_machine: str, text: str, *, from_machine: str, stamp: str) -> Path:
    """Write a message addressed to ``to_machine``; returns the file path created.

    ``stamp`` is a sortable, filename-safe timestamp (e.g. ``20260729T142033Z``) so the recipient's
    directory listing orders naturally. Different senders never collide (the filename carries the
    sender); the *same* sender writing twice within one ``stamp`` tick — e.g. a direct ``send``
    immediately followed by a ``broadcast`` — would, so a ``--dup<n>`` marker is inserted *before*
    ``--from-`` when needed. This never overwrites an existing message, and the marker sits ahead of
    the sender tag so :func:`inbox` still parses a clean sender name.
    """
    box = _box(vault, to_machine)
    box.mkdir(parents=True, exist_ok=True)
    path = box / f"{stamp}--from-{from_machine}.md"
    dup = 2
    while path.exists():
        path = box / f"{stamp}--dup{dup}--from-{from_machine}.md"
        dup += 1
    path.write_text(text.rstrip() + "\n")
    return path


def inbox(vault: Vault, machine: str) -> list[Message]:
    """Unread messages for ``machine``, newest first. Empty if the box is absent."""
    box = _box(vault, machine)
    if not box.is_dir():
        return []
    files = sorted(
        (p for p in box.iterdir() if p.is_file() and p.suffix == ".md"), reverse=True
    )
    messages = []
    for path in files:
        sender = path.stem.split("--from-", 1)[1] if "--from-" in path.stem else "?"
        messages.append(Message(filename=path.name, sender=sender, body=path.read_text().rstrip()))
    return messages


def mark_read(vault: Vault, machine: str) -> int:
    """Move all unread messages into ``read/``; returns how many were moved. Non-destructive."""
    box = _box(vault, machine)
    if not box.is_dir():
        return 0
    read_dir = box / "read"
    read_dir.mkdir(exist_ok=True)
    moved = 0
    for path in [p for p in box.iterdir() if p.is_file() and p.suffix == ".md"]:
        path.rename(read_dir / path.name)
        moved += 1
    return moved
