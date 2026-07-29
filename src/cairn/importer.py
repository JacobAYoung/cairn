"""One-time seeding of the vault from an existing Claude Code setup (``cairn import``).

Copies skill directories and memory ``.md`` files *into* the vault so the vault becomes the
canonical, syncable source of truth. Copy (not move/link) is deliberate: import is non-destructive
— your existing ``~/.claude`` is left intact, and anything already in the vault is skipped rather
than overwritten.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from cairn.vault import Vault


@dataclass(frozen=True)
class ImportResult:
    """What :func:`import_into_vault` did — exact lists for reporting and assertions."""

    skills_imported: tuple[str, ...]
    memories_imported: tuple[str, ...]
    skipped: tuple[str, ...]


def import_into_vault(
    vault: Vault, *, skills_src: Path | None = None, memories_src: Path | None = None
) -> ImportResult:
    """Copy skills (subdirs) and memories (``*.md``) from the given sources into the vault.

    Existing vault entries with the same name are skipped (never overwritten). Absent sources are
    simply ignored, so ``import`` is safe to run with whichever of the two you have.
    """
    vault.ensure_layout()
    skills_imported: list[str] = []
    memories_imported: list[str] = []
    skipped: list[str] = []

    if skills_src and skills_src.is_dir():
        for entry in sorted(p for p in skills_src.iterdir() if p.is_dir()):
            dest = vault.skills_dir / entry.name
            if dest.exists():
                skipped.append(f"skill:{entry.name}")
                continue
            shutil.copytree(entry, dest)
            skills_imported.append(entry.name)

    if memories_src and memories_src.is_dir():
        for entry in sorted(memories_src.glob("*.md")):
            dest = vault.memories_dir / entry.name
            if dest.exists():
                skipped.append(f"memory:{entry.stem}")
                continue
            shutil.copy2(entry, dest)
            memories_imported.append(entry.stem)

    return ImportResult(tuple(skills_imported), tuple(memories_imported), tuple(skipped))
