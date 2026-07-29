"""Environment/host lookups — the impure edge, kept thin and injectable.

These read the real machine (home dir, hostname, ``CAIRN_HOME``). Pure logic elsewhere takes
their *results* as arguments rather than calling these mid-computation, so it stays testable
without a real environment.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

CAIRN_HOME_ENV = "CAIRN_HOME"


def _pointer_file() -> Path:
    """Small file remembering a non-default vault location (e.g. a network drive)."""
    return Path.home() / ".config" / "cairn" / "location"


def default_vault_root() -> Path:
    """Resolve the vault location.

    Order: ``$CAIRN_HOME`` (env, wins) → the pointer file written by ``cairn init --vault-path``
    (e.g. a mounted share) → ``~/.cairn``. This lets the vault live on a shared/network drive or
    git checkout without exporting an env var in every shell.
    """
    override = os.environ.get(CAIRN_HOME_ENV)
    if override:
        return Path(override).expanduser()
    pointer = _pointer_file()
    if pointer.is_file():
        stored = pointer.read_text().strip()
        if stored:
            return Path(stored).expanduser()
    return Path.home() / ".cairn"


def set_vault_location(path: Path) -> Path:
    """Persist ``path`` as the vault location in the pointer file; return the expanded path."""
    resolved = path.expanduser()
    pointer = _pointer_file()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(resolved) + "\n")
    return resolved


def default_machine_name() -> str:
    """This machine's default mailbox name: the short hostname (domain stripped)."""
    short = socket.gethostname().split(".", 1)[0]
    return short or "cairn"
