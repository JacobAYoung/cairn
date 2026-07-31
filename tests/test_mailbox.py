"""Tests for the Tier-0 mailbox (:mod:`cairn.mailbox`) against a real temp vault."""

from __future__ import annotations

from cairn.mailbox import inbox, mark_read, send, wait_for_inbox
from cairn.vault import Vault


class _Clock:
    """A fake monotonic clock whose time advances only when ``sleep`` is called — so a wait loop's
    timeout can be driven deterministically without real waiting."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


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


def test_wait_returns_immediately_when_message_present(tmp_path):
    # Arrange: a message is already waiting
    vault = Vault(tmp_path / "vault")
    send(vault, "laptop", "already here", from_machine="desktop", stamp="20260729T100000Z")
    clock = _Clock()
    polls = []

    # Act
    messages = wait_for_inbox(
        vault, "laptop", now_fn=clock.now, sleep_fn=clock.sleep, poll_fn=lambda: polls.append(1)
    )

    # Assert: returns at once, without sleeping; poll ran exactly once
    assert [m.body for m in messages] == ["already here"]
    assert clock.sleeps == []
    assert len(polls) == 1


def test_wait_polls_until_a_message_appears(tmp_path):
    vault = Vault(tmp_path / "vault")
    clock = _Clock()
    calls = {"n": 0}

    def poll():
        calls["n"] += 1
        if calls["n"] == 3:  # message lands on the third cycle
            send(vault, "laptop", "arrived", from_machine="mini", stamp="20260729T120000Z")

    messages = wait_for_inbox(
        vault, "laptop", now_fn=clock.now, sleep_fn=clock.sleep, poll_fn=poll, interval=2.0
    )

    assert [m.body for m in messages] == ["arrived"]
    assert calls["n"] == 3  # polled each cycle until the message showed
    assert clock.sleeps == [2.0, 2.0]  # slept between the two empty cycles, at the given interval


def test_wait_times_out_and_returns_empty(tmp_path):
    vault = Vault(tmp_path / "vault")
    clock = _Clock()

    messages = wait_for_inbox(
        vault, "laptop", now_fn=clock.now, sleep_fn=clock.sleep, timeout=5.0, interval=2.0
    )

    assert messages == []
    assert clock.sleeps == [2.0, 2.0, 2.0]  # slept at t=0,2,4; at t=6 the 5s deadline is past
    assert clock.now() == 6.0


def test_wait_timeout_zero_returns_immediately_when_empty(tmp_path):
    vault = Vault(tmp_path / "vault")
    clock = _Clock()

    messages = wait_for_inbox(
        vault, "laptop", now_fn=clock.now, sleep_fn=clock.sleep, timeout=0.0
    )

    assert messages == []
    assert clock.sleeps == []  # never sleeps — checks once, deadline already reached


def test_mark_read_moves_messages_and_clears_inbox(tmp_path):
    vault = Vault(tmp_path / "vault")
    send(vault, "laptop", "a", from_machine="desktop", stamp="20260729T090000Z")
    send(vault, "laptop", "b", from_machine="desktop", stamp="20260729T100000Z")

    moved = mark_read(vault, "laptop")

    assert moved == 2
    assert inbox(vault, "laptop") == []  # nothing unread left
    # messages preserved under read/
    assert len(list((vault.mailbox_dir / "laptop" / "read").glob("*.md"))) == 2
