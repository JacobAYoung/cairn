"""Tests for warm-start checkpoints (:mod:`cairn.checkpoints`) against a real temp vault."""

from __future__ import annotations

from cairn.checkpoints import latest_brief, write_checkpoint
from cairn.vault import Vault


def test_write_creates_stamped_block_and_returns_path(tmp_path):
    vault = Vault(tmp_path / "vault")

    path = write_checkpoint(
        vault, "proj", "decided X; TODO Y", machine="desktop", now="2026-07-29T10:00"
    )

    assert path == vault.session_notes_dir / "proj.md"
    content = path.read_text()
    assert content.startswith("## 2026-07-29T10:00 — desktop\n")
    assert "decided X; TODO Y" in content


def test_second_checkpoint_is_prepended_newest_first(tmp_path):
    vault = Vault(tmp_path / "vault")
    write_checkpoint(vault, "proj", "first", machine="desktop", now="2026-07-29T10:00")
    write_checkpoint(vault, "proj", "second", machine="laptop", now="2026-07-29T11:00")

    content = (vault.session_notes_dir / "proj.md").read_text()
    # newest block on top
    assert content.index("second") < content.index("first")
    assert content.startswith("## 2026-07-29T11:00 — laptop")


def test_latest_brief_returns_most_recent_block(tmp_path):
    vault = Vault(tmp_path / "vault")
    write_checkpoint(vault, "proj", "first", machine="desktop", now="2026-07-29T10:00")
    write_checkpoint(vault, "proj", "second", machine="laptop", now="2026-07-29T11:00")

    brief = latest_brief(vault, "proj")
    assert brief.startswith("## 2026-07-29T11:00 — laptop")
    assert "second" in brief
    assert "first" not in brief  # only the newest block


def test_latest_brief_none_when_absent(tmp_path):
    assert latest_brief(Vault(tmp_path / "vault"), "proj") is None
