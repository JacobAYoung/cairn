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


def default_vault_root() -> Path:
    """The vault location: ``$CAIRN_HOME`` if set, else ``~/.cairn``."""
    override = os.environ.get(CAIRN_HOME_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cairn"


def default_machine_name() -> str:
    """This machine's default mailbox name: the short hostname (domain stripped)."""
    short = socket.gethostname().split(".", 1)[0]
    return short or "cairn"
