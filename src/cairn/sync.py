"""The sync-backend seam.

Everything else in Cairn talks to sync through one tiny interface — :class:`SyncBackend` with
``pull`` / ``push`` / ``status`` — so adding a backend is a new class, not an edit elsewhere
(SPEC Appendix C). Cairn never *implements* file sync; it drives what the user already trusts.

MVP backends:
- ``off``    — single machine; no-op.
- ``folder`` — the vault lives in an already-synced dir (iCloud/Dropbox); the OS syncs it, so
  ``pull``/``push`` are no-ops and ``status`` just reports whether the folder is present.
- ``syncthing`` — the Syncthing daemon continuously syncs the folder, so from Cairn's side it
  behaves like ``folder`` (no active push/pull to perform).

``git`` performs active pull/commit/push via an injected command-runner. Per SPEC, ``push`` is
best-effort and must never block or corrupt state: the default runner has a timeout, and network
failures are swallowed (a no-op backend satisfies this trivially; git catches subprocess errors).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

# A runner executes a command in a directory and returns the completed process. Injected so
# GitSync's git invocations (exact argv, order, count) are assertable without touching git.
CommandRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]

GIT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class SyncStatus:
    """A snapshot of sync health for ``cairn status``."""

    mode: str
    ok: bool
    detail: str


@runtime_checkable
class SyncBackend(Protocol):
    """Drives an external sync mechanism over the vault root."""

    def pull(self) -> None:
        """Best-effort: bring the local vault up to date before a read. Never raises on network."""
        ...

    def push(self, message: str) -> None:
        """Best-effort: publish local changes after a write. Never blocks or raises on network."""
        ...

    def status(self) -> SyncStatus:
        """Report current sync health without side effects."""
        ...


class OffSync:
    """No sync — single-machine use. Every operation is a no-op."""

    mode = "off"

    def pull(self) -> None:
        return None

    def push(self, message: str) -> None:
        return None

    def status(self) -> SyncStatus:
        return SyncStatus(mode=self.mode, ok=True, detail="sync disabled")


class FolderSync:
    """Vault lives in an OS/cloud-synced folder; Cairn performs no active sync itself."""

    def __init__(self, root: Path, *, mode: str = "folder") -> None:
        self._root = root
        self.mode = mode

    def pull(self) -> None:
        return None

    def push(self, message: str) -> None:
        return None

    def status(self) -> SyncStatus:
        if self._root.is_dir():
            return SyncStatus(mode=self.mode, ok=True, detail=f"synced folder at {self._root}")
        return SyncStatus(mode=self.mode, ok=False, detail=f"folder missing: {self._root}")


def _default_runner(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing output, with a bounded timeout so sync never hangs the CLI."""
    return subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )


class GitSync:
    """Active git-backed sync: ``pull --rebase`` before reads, add/commit/push after writes.

    Network operations are best-effort: a failing git call (offline, no remote, timeout) is
    swallowed so it never blocks or crashes the CLI — the local write already succeeded.
    """

    mode = "git"

    def __init__(self, root: Path, *, runner: CommandRunner = _default_runner) -> None:
        self._root = root
        self._run = runner

    def _safe(self, *args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return self._run(args, self._root)
        except (subprocess.SubprocessError, OSError):
            return None

    def pull(self) -> None:
        self._safe("git", "pull", "--rebase")

    def push(self, message: str) -> None:
        self._safe("git", "add", "-A")
        self._safe("git", "commit", "-m", message)  # non-zero if nothing to commit — fine
        self._safe("git", "push")

    def status(self) -> SyncStatus:
        result = self._safe("git", "status", "--porcelain")
        if result is None:
            return SyncStatus(mode=self.mode, ok=False, detail="git unavailable")
        dirty = bool(result.stdout.strip())
        return SyncStatus(mode=self.mode, ok=True, detail="dirty" if dirty else "clean")


def make_sync_backend(mode: str, root: Path) -> SyncBackend:
    """Construct the backend for a resolved ``[sync].mode``.

    ``folder``/``syncthing`` → :class:`FolderSync` (an external process owns the syncing);
    ``git`` → :class:`GitSync`; ``off`` → :class:`OffSync`. Unknown modes are rejected by config
    validation before reaching here, so this only sees valid modes.
    """
    if mode in ("folder", "syncthing"):
        return FolderSync(root, mode=mode)
    if mode == "git":
        return GitSync(root)
    return OffSync()
