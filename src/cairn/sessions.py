"""Same-machine session roster (see docs/SESSIONS.md).

Several Claude Code sessions can run on **one** machine, share a single vault, and tell themselves
apart by *mailbox identity* (``$CAIRN_MACHINE``, resolved in :mod:`cairn.system`). This module is
the **roster**: a directory of tiny JSON presence files — one per session — so sessions can

* discover each other (``cairn session ls``), and
* fan a message out to every peer (``cairn broadcast``)

with **no daemon, no ports, no admin** — exactly the Tier-0 philosophy of :mod:`cairn.mailbox`,
which handles the actual message delivery. The roster only tracks *who exists*.

Presence is **machine-local runtime state**, not portable config: every record carries the real
``host`` it was created on, so a synced vault (Syncthing/folder) never conflates one machine's
sessions with another's — callers filter by ``host`` to see only local peers. Records are plain
files (the filesystem is the source of truth); a corrupt or foreign file is skipped, never fatal.

The logic here is pure: it takes an injected ``now`` (an ISO-8601 string, as the CLI already
produces for timestamps) rather than reading the clock itself, so behavior is exactly testable.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from cairn.errors import CairnError
from cairn.vault import Vault

#: A session is "live" if its last check-in is within this many seconds; older is "stale".
DEFAULT_STALE_SECONDS = 15 * 60

#: Session names become filenames and mailbox addresses, so they are constrained to a safe,
#: traversal-proof alphabet: start alphanumeric, then letters/digits/dot/underscore/hyphen. This
#: forbids ``/``, ``..`` and leading separators — no path can escape ``sessions/``.
_VALID_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class SessionRecord:
    """One registered session's presence.

    ``name`` is its mailbox identity (the ``$CAIRN_MACHINE`` value); ``host`` is the real machine
    it runs on (short hostname); ``project`` is the working directory it registered from; the two
    timestamps are naive-local ISO-8601 strings (``created_utc`` fixed at first registration,
    ``last_seen_utc`` refreshed on every check-in).
    """

    name: str
    host: str
    project: str
    created_utc: str
    last_seen_utc: str


def validate_name(name: str) -> str:
    """Return ``name`` unchanged if it is a legal session name, else raise :class:`CairnError`.

    Guards both the filename and the mailbox path against traversal (``../``) and separators.
    """
    if not _VALID_NAME.fullmatch(name):
        raise CairnError(
            f"invalid session name {name!r}: use letters, digits, '.', '_' or '-' "
            "(must start with a letter or digit)"
        )
    return name


def _record_path(vault: Vault, name: str):
    return vault.sessions_dir / f"{validate_name(name)}.json"


def _read_record(path) -> SessionRecord | None:
    """Parse a presence file into a :class:`SessionRecord`, or ``None`` if it is unreadable.

    A malformed/foreign file must never break a listing, so every failure mode (bad JSON, missing
    field, wrong type, I/O error) collapses to ``None`` for the caller to skip.
    """
    try:
        data = json.loads(path.read_text())
        return SessionRecord(
            name=str(data["name"]),
            host=str(data["host"]),
            project=str(data["project"]),
            created_utc=str(data["created_utc"]),
            last_seen_utc=str(data["last_seen_utc"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return None


def register(vault: Vault, name: str, *, host: str, project: str, now: str) -> SessionRecord:
    """Create or refresh the presence file for ``name``; return the stored record.

    Idempotent and doubles as a heartbeat: re-registering an existing session refreshes
    ``last_seen_utc`` (and ``project``/``host``) but preserves the original ``created_utc``. A
    previously-corrupt file is simply overwritten with a fresh, valid record.
    """
    path = _record_path(vault, name)
    vault.sessions_dir.mkdir(parents=True, exist_ok=True)

    created = now
    if path.is_file():
        existing = _read_record(path)
        if existing is not None:
            created = existing.created_utc

    record = SessionRecord(
        name=name, host=host, project=project, created_utc=created, last_seen_utc=now
    )
    path.write_text(json.dumps(asdict(record), indent=2) + "\n")
    return record


def end(vault: Vault, name: str) -> bool:
    """Remove ``name`` from the roster; ``True`` if a record existed, ``False`` otherwise."""
    path = _record_path(vault, name)
    if path.is_file():
        path.unlink()
        return True
    return False


def roster(vault: Vault, *, host: str | None = None) -> list[SessionRecord]:
    """Registered sessions, sorted by name. If ``host`` is given, only that machine's sessions.

    Corrupt/foreign files are skipped. Empty list when the roster directory is absent.
    """
    directory = vault.sessions_dir
    if not directory.is_dir():
        return []
    records = []
    for path in sorted(directory.glob("*.json")):
        record = _read_record(path)
        if record is None:
            continue
        if host is None or record.host == host:
            records.append(record)
    return records


def seconds_between(earlier_iso: str, later_iso: str) -> float:
    """Seconds from ``earlier_iso`` to ``later_iso`` (both naive-local ISO-8601).

    Negative if ``later_iso`` actually precedes ``earlier_iso``. Raises :class:`ValueError` on an
    unparseable timestamp — callers pass timestamps they themselves wrote, so that is a real bug.
    """
    return (datetime.fromisoformat(later_iso) - datetime.fromisoformat(earlier_iso)).total_seconds()


def is_live(record: SessionRecord, *, now: str, stale_seconds: int = DEFAULT_STALE_SECONDS) -> bool:
    """Whether ``record`` checked in within ``stale_seconds`` of ``now`` (a clock skew into the
    future still counts as live)."""
    return seconds_between(record.last_seen_utc, now) <= stale_seconds


def prune(
    vault: Vault,
    *,
    now: str,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
    host: str | None = None,
) -> list[str]:
    """Delete sessions last seen more than ``stale_seconds`` ago; return removed names, sorted."""
    removed = []
    for record in roster(vault, host=host):
        if not is_live(record, now=now, stale_seconds=stale_seconds):
            if end(vault, record.name):
                removed.append(record.name)
    return sorted(removed)
