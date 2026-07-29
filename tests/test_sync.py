"""Tests for the sync-backend seam (:mod:`cairn.sync`).

For the no-op backends we assert the reported status data. For git we inject a recording runner
and assert the EXACT git commands, their order, and their count — the interaction assertions the
standard requires — plus that network failures are swallowed (best-effort, never propagate).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cairn.sync import (
    FolderSync,
    GitSync,
    OffSync,
    SyncStatus,
    make_sync_backend,
)


class RecordingRunner:
    """Records every (argv, cwd) and returns a canned CompletedProcess."""

    def __init__(self, stdout: str = "") -> None:
        self.calls: list[list[str]] = []
        self._stdout = stdout

    def __call__(self, args, cwd) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        return subprocess.CompletedProcess(
            args=list(args), returncode=0, stdout=self._stdout, stderr=""
        )


def test_off_sync_is_noop_and_reports_disabled():
    backend = OffSync()
    # No-ops don't raise
    assert backend.pull() is None
    assert backend.push("msg") is None
    # Status data
    status = backend.status()
    assert (status.mode, status.ok, status.detail) == ("off", True, "sync disabled")


def test_folder_sync_status_reflects_presence(tmp_path):
    present = FolderSync(tmp_path).status()
    assert present == SyncStatus(mode="folder", ok=True, detail=f"synced folder at {tmp_path}")

    missing = FolderSync(tmp_path / "gone", mode="syncthing").status()
    assert missing.mode == "syncthing" and missing.ok is False


def test_git_push_runs_add_commit_push_in_order_with_exact_args():
    # Arrange
    runner = RecordingRunner()
    backend = GitSync(Path("/repo"), runner=runner)

    # Act
    backend.push("cairn: checkpoint")

    # Assert INTERACTION: exactly three git calls, in order, with exact argv
    assert runner.calls == [
        ["git", "add", "-A"],
        ["git", "commit", "-m", "cairn: checkpoint"],
        ["git", "push"],
    ]


def test_git_pull_rebases():
    runner = RecordingRunner()
    GitSync(Path("/repo"), runner=runner).pull()
    assert runner.calls == [["git", "pull", "--rebase"]]


def test_git_status_parses_porcelain_into_clean_or_dirty():
    clean = GitSync(Path("/repo"), runner=RecordingRunner(stdout="")).status()
    assert clean.ok is True and clean.detail == "clean"

    dirty = GitSync(Path("/repo"), runner=RecordingRunner(stdout=" M file.md\n")).status()
    assert dirty.detail == "dirty"


def test_git_push_swallows_network_failure():
    # Arrange: a runner that fails as git would when offline / no remote
    def failing(args, cwd):
        raise subprocess.SubprocessError("no upstream")

    backend = GitSync(Path("/repo"), runner=failing)

    # Act / Assert: best-effort — push must not propagate
    assert backend.push("m") is None
    # And status surfaces the failure rather than crashing
    assert backend.status().ok is False


def test_factory_maps_mode_to_backend(tmp_path):
    assert make_sync_backend("off", tmp_path).mode == "off"
    assert make_sync_backend("folder", tmp_path).mode == "folder"
    assert make_sync_backend("syncthing", tmp_path).mode == "syncthing"
    assert make_sync_backend("git", tmp_path).mode == "git"
    assert isinstance(make_sync_backend("git", tmp_path), GitSync)
    assert isinstance(make_sync_backend("off", tmp_path), OffSync)
