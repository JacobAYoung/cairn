"""Wire Cairn into a Claude Code install: the bundled skill + the SessionStart hook.

Both operations are **idempotent and non-destructive** — they merge into whatever's already in
``~/.claude`` rather than replacing it. This is what ``cairn init`` uses to make Cairn "just work"
after a one-time setup; kept in its own module so the file-editing logic is unit-tested against
temp dirs before it ever touches a real config.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

BUNDLED_SKILL_DIR = Path(__file__).parent / "data" / "skill"
SKILL_NAME = "cairn"
HOOK_COMMAND = "cairn session-start"
HOOK_TIMEOUT_SECONDS = 15


def install_skill(skills_dir: Path) -> Path:
    """Copy the bundled Cairn skill into ``skills_dir/cairn`` (refreshing any prior copy)."""
    dest = skills_dir / SKILL_NAME
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BUNDLED_SKILL_DIR, dest)
    return dest


def _hook_already_installed(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("SessionStart", []):
        for hook in entry.get("hooks", []):
            if hook.get("command") == HOOK_COMMAND:
                return True
    return False


def install_session_start_hook(settings_path: Path) -> bool:
    """Merge the Cairn SessionStart hook into ``settings.json``. Returns True if it was added.

    Idempotent: if a hook running ``cairn session-start`` is already present, nothing changes and
    False is returned. All other settings and hooks are preserved.
    """
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    if _hook_already_installed(settings):
        return False

    entry = {
        "matcher": "startup|resume",
        "hooks": [
            {"type": "command", "command": HOOK_COMMAND, "timeout": HOOK_TIMEOUT_SECONDS}
        ],
    }
    settings.setdefault("hooks", {}).setdefault("SessionStart", []).append(entry)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return True
