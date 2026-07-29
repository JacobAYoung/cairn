"""Warm-start checkpoints (SPEC Pillar 4).

At the end of a work session Claude writes a short brief (decisions, open threads, where things
live); Cairn persists it, newest-first, in the synced vault so the *next* session — on any machine
— can load it and skip expensive re-exploration. Cairn does not scrape the transcript; the caller
supplies the text (Claude has the context, Cairn just stores + indexes it).

Storage: ``session-notes/<project>.md``, one dated + machine-stamped block per checkpoint, newest
on top. Because it lives in the vault, a checkpoint written on one machine is already on the other.
"""

from __future__ import annotations

from pathlib import Path

from cairn.vault import Vault


def _notes_path(vault: Vault, project_key: str) -> Path:
    return vault.session_notes_dir / f"{project_key}.md"


def write_checkpoint(
    vault: Vault, project_key: str, text: str, *, machine: str, now: str
) -> Path:
    """Prepend a stamped checkpoint block for ``project_key``; returns the notes file path."""
    vault.ensure_layout()
    path = _notes_path(vault, project_key)
    block = f"## {now} — {machine}\n\n{text.strip()}\n"
    existing = path.read_text() if path.exists() else ""
    path.write_text(block + ("\n" + existing if existing else ""))
    return path


def latest_brief(vault: Vault, project_key: str) -> str | None:
    """Return the most recent checkpoint block (with its header), or None if there are none."""
    path = _notes_path(vault, project_key)
    if not path.exists():
        return None
    # Newest block is at the top; a block runs until the next "## " header.
    first_block = path.read_text().split("\n## ", 1)[0].strip()
    return first_block or None
