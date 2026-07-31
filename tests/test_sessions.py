"""Tests for the same-machine session roster (:mod:`cairn.sessions`) against a real temp vault.

Timestamps are injected as explicit ISO-8601 strings so presence/age logic is asserted on exact
values, never on a real clock.
"""

from __future__ import annotations

import json

import pytest

from cairn import sessions
from cairn.errors import CairnError
from cairn.vault import Vault

T_0900 = "2026-07-30T09:00:00"
T_1000 = "2026-07-30T10:00:00"
T_1000_30 = "2026-07-30T10:00:30"


def _vault(tmp_path):
    return Vault(tmp_path / "vault")


# --- register -------------------------------------------------------------------------------


def test_register_writes_record_with_exact_fields(tmp_path):
    vault = _vault(tmp_path)

    record = sessions.register(
        vault, "sessionA", host="mac-mini", project="Fortress-JMS", now=T_1000
    )

    # Return value: created == last_seen at first registration
    assert record == sessions.SessionRecord(
        name="sessionA",
        host="mac-mini",
        project="Fortress-JMS",
        created_utc=T_1000,
        last_seen_utc=T_1000,
    )
    # On-disk: exactly one file, holding exactly those fields
    files = list(vault.sessions_dir.glob("*.json"))
    assert [p.name for p in files] == ["sessionA.json"]
    assert json.loads(files[0].read_text()) == {
        "name": "sessionA",
        "host": "mac-mini",
        "project": "Fortress-JMS",
        "created_utc": T_1000,
        "last_seen_utc": T_1000,
    }


def test_reregister_refreshes_last_seen_but_preserves_created(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "sessionA", host="mac-mini", project="proj1", now=T_1000)

    updated = sessions.register(vault, "sessionA", host="mac-mini", project="proj2", now=T_1000_30)

    # created_utc frozen at first registration; last_seen + project refreshed
    assert updated.created_utc == T_1000
    assert updated.last_seen_utc == T_1000_30
    assert updated.project == "proj2"
    # Heartbeat, not a duplicate: still a single file
    assert len(list(vault.sessions_dir.glob("*.json"))) == 1


def test_register_overwrites_corrupt_file(tmp_path):
    vault = _vault(tmp_path)
    vault.sessions_dir.mkdir(parents=True)
    (vault.sessions_dir / "sessionA.json").write_text("{ not json")

    record = sessions.register(vault, "sessionA", host="h", project="p", now=T_1000)

    assert record.created_utc == T_1000  # fresh created, corrupt value ignored
    assert sessions.roster(vault) == [record]


@pytest.mark.parametrize("bad", ["../evil", "a/b", "..", "", ".hidden", "no space", "-lead"])
def test_register_rejects_unsafe_names(tmp_path, bad):
    with pytest.raises(CairnError, match="invalid session name"):
        sessions.register(_vault(tmp_path), bad, host="h", project="p", now=T_1000)
    # Nothing was written for a rejected name
    assert sessions.roster(_vault(tmp_path)) == []


@pytest.mark.parametrize("good", ["sessionA", "s1", "a.b-c_d", "9lives"])
def test_register_accepts_safe_names(tmp_path, good):
    record = sessions.register(_vault(tmp_path), good, host="h", project="p", now=T_1000)
    assert record.name == good


# --- end ------------------------------------------------------------------------------------


def test_end_removes_existing_and_reports_true(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "sessionA", host="h", project="p", now=T_1000)

    assert sessions.end(vault, "sessionA") is True
    assert sessions.roster(vault) == []


def test_end_missing_reports_false(tmp_path):
    assert sessions.end(_vault(tmp_path), "ghost") is False


# --- roster ---------------------------------------------------------------------------------


def test_roster_sorted_by_name(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "zeta", host="h", project="p", now=T_1000)
    sessions.register(vault, "alpha", host="h", project="p", now=T_1000)

    assert [r.name for r in sessions.roster(vault)] == ["alpha", "zeta"]


def test_roster_filters_by_host(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "here", host="mac-mini", project="p", now=T_1000)
    sessions.register(vault, "there", host="laptop", project="p", now=T_1000)

    # Only the requested host's sessions come back — a synced vault never leaks foreign presence
    assert [r.name for r in sessions.roster(vault, host="mac-mini")] == ["here"]


def test_roster_skips_corrupt_files_without_crashing(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "good", host="h", project="p", now=T_1000)
    (vault.sessions_dir / "bad.json").write_text("}{")

    assert [r.name for r in sessions.roster(vault)] == ["good"]


def test_roster_empty_when_dir_absent(tmp_path):
    assert sessions.roster(_vault(tmp_path)) == []


# --- time helpers ---------------------------------------------------------------------------


def test_seconds_between_exact(tmp_path):
    assert sessions.seconds_between(T_1000, T_1000_30) == 30.0
    assert sessions.seconds_between(T_1000_30, T_1000) == -30.0


def test_is_live_boundary_and_future(tmp_path):
    fresh = sessions.SessionRecord("s", "h", "p", T_1000, T_1000)

    # Exactly at the window edge counts as live; one second past does not
    assert sessions.is_live(fresh, now=T_1000, stale_seconds=30) is True
    assert sessions.is_live(fresh, now=T_1000_30, stale_seconds=30) is True
    assert sessions.is_live(fresh, now="2026-07-30T10:00:31", stale_seconds=30) is False
    # A last_seen in the future (clock skew) is still live
    assert sessions.is_live(fresh, now=T_0900, stale_seconds=30) is True


# --- prune ----------------------------------------------------------------------------------


def test_prune_removes_only_stale_and_returns_sorted_names(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "stale-b", host="h", project="p", now=T_0900)  # 1h old
    sessions.register(vault, "stale-a", host="h", project="p", now=T_0900)  # 1h old
    sessions.register(vault, "fresh", host="h", project="p", now=T_1000)  # just now

    removed = sessions.prune(vault, now=T_1000, stale_seconds=sessions.DEFAULT_STALE_SECONDS)

    assert removed == ["stale-a", "stale-b"]  # sorted, both stale ones
    assert [r.name for r in sessions.roster(vault)] == ["fresh"]  # live one survives


def test_prune_respects_host_filter(tmp_path):
    vault = _vault(tmp_path)
    sessions.register(vault, "mine", host="mac-mini", project="p", now=T_0900)
    sessions.register(vault, "theirs", host="laptop", project="p", now=T_0900)

    removed = sessions.prune(vault, now=T_1000, stale_seconds=1, host="mac-mini")

    assert removed == ["mine"]
    # The other host's (also stale) session is untouched — not this machine's business
    assert [r.name for r in sessions.roster(vault)] == ["theirs"]
