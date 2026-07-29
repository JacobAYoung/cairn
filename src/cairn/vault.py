"""The vault: the synced source of truth at ``~/.cairn/``.

Layout (see SPEC.md):

    ~/.cairn/
      skills/         one subdirectory per skill (a Claude skill is a dir containing SKILL.md)
      memories/       one <name>.md per memory
      session-notes/  warm-start checkpoints
      mailbox/        Tier-0 cross-machine messages
      cairn.toml, profiles.toml

The vault owns *path resolution and inventory only* — it does not read/parse config (that's
:mod:`cairn.config`) or perform activation (that's the ``use`` command). Inventory is a plain
directory scan: dependency-free and fast enough for personal scale. A SQLite/FTS index is
introduced only if/when ``recall`` search lands (see RESEARCH.md §4) — files stay the truth.
"""

from __future__ import annotations

from pathlib import Path

from cairn.errors import CairnError

SUBDIRS = ("skills", "memories", "session-notes", "mailbox")


class Vault:
    """Resolves paths inside ``~/.cairn/`` and lists what's stored there."""

    def __init__(self, root: Path) -> None:
        self.root = root

    # --- paths --------------------------------------------------------------------------
    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def memories_dir(self) -> Path:
        return self.root / "memories"

    @property
    def session_notes_dir(self) -> Path:
        return self.root / "session-notes"

    @property
    def mailbox_dir(self) -> Path:
        return self.root / "mailbox"

    @property
    def cairn_config_path(self) -> Path:
        return self.root / "cairn.toml"

    @property
    def profiles_path(self) -> Path:
        return self.root / "profiles.toml"

    def exists(self) -> bool:
        return self.root.is_dir()

    def ensure_layout(self) -> None:
        """Create the vault root and all standard subdirectories (idempotent)."""
        for name in SUBDIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # --- inventory ----------------------------------------------------------------------
    def list_skills(self) -> list[str]:
        """Skill names (subdirectory names under ``skills/``), sorted. Empty if none/absent."""
        if not self.skills_dir.is_dir():
            return []
        return sorted(p.name for p in self.skills_dir.iterdir() if p.is_dir())

    def list_memories(self) -> list[str]:
        """Memory names (``*.md`` stems under ``memories/``), sorted. Empty if none/absent."""
        if not self.memories_dir.is_dir():
            return []
        return sorted(p.stem for p in self.memories_dir.glob("*.md"))

    # --- resolution (used by activation; raises so a bad profile fails before any change) --
    def skill_path(self, name: str) -> Path:
        """Absolute path to a skill directory, or :class:`CairnError` if it isn't in the vault."""
        path = self.skills_dir / name
        if not path.is_dir():
            raise CairnError(f"skill {name!r} not found in vault ({self.skills_dir})")
        return path

    def memory_path(self, name: str) -> Path:
        """Absolute path to a memory file, or :class:`CairnError` if it isn't in the vault."""
        path = self.memories_dir / f"{name}.md"
        if not path.is_file():
            raise CairnError(f"memory {name!r} not found in vault ({self.memories_dir})")
        return path
