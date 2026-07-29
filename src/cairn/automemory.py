"""Sync Claude's own auto-memory across machines (SPEC Appendix D — the strongest differentiator).

Claude Code's auto-memory is machine-local by default, but its location is relocatable via the
``autoMemoryDirectory`` setting. Pointing it at a per-project folder *inside the synced vault* makes
Claude's accumulated learnings follow you between machines — a gap native doesn't fill.

This edits ``.claude/settings.local.json`` (project-scoped) only; enabling/disabling is a single
key, and the target folder is created in the vault so it exists to sync.
"""

from __future__ import annotations

import json
from pathlib import Path

from cairn.vault import Vault

SETTING_KEY = "autoMemoryDirectory"


def _settings_path(project_dir: Path) -> Path:
    return project_dir / ".claude" / "settings.local.json"


def _load(project_dir: Path) -> dict:
    path = _settings_path(project_dir)
    return json.loads(path.read_text()) if path.exists() else {}


def _save(project_dir: Path, settings: dict) -> None:
    path = _settings_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")


def enable(vault: Vault, project_dir: Path, project_key: str) -> Path:
    """Point auto-memory at ``<vault>/auto-memory/<project_key>``; return that target path."""
    target = vault.root / "auto-memory" / project_key
    target.mkdir(parents=True, exist_ok=True)
    settings = _load(project_dir)
    settings[SETTING_KEY] = str(target)
    _save(project_dir, settings)
    return target


def disable(project_dir: Path) -> bool:
    """Remove the auto-memory redirection. Returns True if a setting was present and removed."""
    settings = _load(project_dir)
    if SETTING_KEY not in settings:
        return False
    del settings[SETTING_KEY]
    _save(project_dir, settings)
    return True
