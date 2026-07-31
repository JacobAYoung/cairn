"""Tier-0 cross-machine mailbox (SPEC Appendix C).

Messaging with **no daemon, no ports, no admin** — just files in the synced vault. ``send`` drops
a timestamped file into ``mailbox/<to-machine>/``; the other machine's ``inbox`` lists them
newest-first. Two machines never collide: each writes a distinct filename (its own timestamp +
sender), which is why the inbox is a directory of files, not one appended file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cairn.vault import Vault

#: How often ``wait_for_inbox`` re-checks the box while blocking (seconds). A short poll rather
#: than a kernel filesystem watch keeps the feature dependency-free and portable; 1s is well below
#: human conversational latency and costs nothing (the *subprocess* waits, not the caller).
DEFAULT_POLL_INTERVAL = 1.0


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


def wait_for_inbox(
    vault: Vault,
    machine: str,
    *,
    now_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
    poll_fn: Callable[[], object] = lambda: None,
    timeout: float | None = None,
    interval: float = DEFAULT_POLL_INTERVAL,
) -> list[Message]:
    """Block until ``machine`` has at least one message, then return them (newest first).

    This is the receive half of a near-push loop: rather than the caller polling on a timer, it
    parks here until mail lands. ``poll_fn`` runs once per cycle *before* each check — the CLI
    passes the sync backend's ``pull`` so a synced vault also surfaces messages that arrived on
    another machine. ``timeout`` (seconds) caps the wait: ``None`` blocks indefinitely, and on
    expiry an empty list is returned (never an exception) so the caller can loop or give up.

    Time and sleep are injected (``now_fn`` should be monotonic, e.g. ``time.monotonic``) so the
    loop is exactly unit-testable without real waiting. A message already waiting returns
    immediately — ``sleep_fn`` is never called and no time is burned.
    """
    start = now_fn()
    while True:
        poll_fn()
        messages = inbox(vault, machine)
        if messages:
            return messages
        if timeout is not None and now_fn() - start >= timeout:
            return []
        sleep_fn(interval)


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
