"""Tests for handoff payloads (:mod:`cairn.handoff`)."""

from __future__ import annotations

from cairn.handoff import build_handoff_payload, is_handoff, latest_handoff
from cairn.mailbox import Message


def test_payload_includes_marker_project_profiles_note_and_brief():
    payload = build_handoff_payload(
        "datalens", ["dev-heavy"], "watch the migration", "## brief\ndid X"
    )
    assert payload.startswith("### CAIRN HANDOFF")
    assert "project: datalens" in payload
    assert "profiles: dev-heavy" in payload
    assert "note: watch the migration" in payload
    assert "did X" in payload


def test_payload_handles_no_profiles_and_no_brief():
    payload = build_handoff_payload("proj", [], None, None)
    assert "profiles: (none)" in payload
    assert "(no checkpoint saved)" in payload
    assert "note:" not in payload


def test_is_handoff_detects_marker():
    assert is_handoff("### CAIRN HANDOFF\nproject: x") is True
    assert is_handoff("just a normal message") is False


def test_latest_handoff_picks_newest_handoff_skipping_others():
    messages = [
        Message("2--from-a.md", "a", "plain note"),  # newest, not a handoff
        Message("1--from-b.md", "b", "### CAIRN HANDOFF\nproject: p"),  # older handoff
    ]
    picked = latest_handoff(messages)
    assert picked is not None
    assert picked.sender == "b"


def test_latest_handoff_none_when_no_handoffs():
    assert latest_handoff([Message("1--from-a.md", "a", "hi")]) is None
