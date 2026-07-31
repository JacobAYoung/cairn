"""Tests for the Tier-0 mailbox (:mod:`cairn.mailbox`) against a real temp vault."""

from __future__ import annotations

from cairn.mailbox import inbox, mark_read, send
from cairn.vault import Vault


def test_send_writes_named_file_with_body(tmp_path):
    vault = Vault(tmp_path / "vault")

    path = send(
        vault, "laptop", "context: refactor done", from_machine="desktop", stamp="20260729T100000Z"
    )

    # Addressed to laptop's box, filename encodes stamp + sender
    assert path == vault.mailbox_dir / "laptop" / "20260729T100000Z--from-desktop.md"
    assert path.read_text() == "context: refactor done\n"


def test_inbox_lists_newest_first_with_sender(tmp_path):
    vault = Vault(tmp_path / "vault")
    send(vault, "laptop", "older", from_machine="desktop", stamp="20260729T090000Z")
    send(vault, "laptop", "newer", from_machine="mini", stamp="20260729T120000Z")

    messages = inbox(vault, "laptop")

    # Newest first; sender parsed from filename
    assert [m.body for m in messages] == ["newer", "older"]
    assert messages[0].sender == "mini"
    assert messages[1].sender == "desktop"


def test_same_sender_same_stamp_does_not_overwrite(tmp_path):
    # Regression: a direct send followed by a broadcast (same sender, same second) must not clobber.
    vault = Vault(tmp_path / "vault")

    first = send(vault, "laptop", "direct hello", from_machine="desktop", stamp="20260729T100000Z")
    second = send(vault, "laptop", "broadcast hi", from_machine="desktop", stamp="20260729T100000Z")

    # Two distinct files on disk, neither lost
    assert first != second
    assert second.name == "20260729T100000Z--dup2--from-desktop.md"
    assert {m.body for m in inbox(vault, "laptop")} == {"direct hello", "broadcast hi"}
    # The dup marker sits before the sender tag, so the parsed sender stays clean
    assert all(m.sender == "desktop" for m in inbox(vault, "laptop"))


def test_inbox_empty_when_no_box(tmp_path):
    assert inbox(Vault(tmp_path / "vault"), "laptop") == []


def test_mark_read_moves_messages_and_clears_inbox(tmp_path):
    vault = Vault(tmp_path / "vault")
    send(vault, "laptop", "a", from_machine="desktop", stamp="20260729T090000Z")
    send(vault, "laptop", "b", from_machine="desktop", stamp="20260729T100000Z")

    moved = mark_read(vault, "laptop")

    assert moved == 2
    assert inbox(vault, "laptop") == []  # nothing unread left
    # messages preserved under read/
    assert len(list((vault.mailbox_dir / "laptop" / "read").glob("*.md"))) == 2
