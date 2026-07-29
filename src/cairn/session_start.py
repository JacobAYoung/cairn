"""Logic for the ``SessionStart`` hook — the automation that makes Cairn "just work".

Claude Code runs the hook *before* skills/CLAUDE.md load, and honors ``reloadSkills`` and
``additionalContext`` in the returned JSON. So on every session this:

1. **Auto-activates the default profile** (from ``[defaults].profile``) if nothing is active yet —
   so a project is configured without ever running ``cairn use``. An explicit prior activation is
   respected, never overridden.
2. **Loads the newest warm-start brief** into context automatically.
3. Sets ``reloadSkills`` so a just-linked bundle takes effect *this* session, not the next.

This function is pure enough to test directly (it takes the vault/config/profiles as arguments);
the command wrapper serializes the result and guarantees a broken hook never breaks the session.
"""

from __future__ import annotations

from pathlib import Path

from cairn.activation import activate, read_state, resolve_bundle
from cairn.checkpoints import latest_brief
from cairn.config import CairnConfig, Profile
from cairn.vault import Vault


def build_session_start_output(
    vault: Vault,
    project_dir: Path,
    config: CairnConfig,
    profiles: dict[str, Profile],
    *,
    now: str,
) -> dict:
    """Return the ``hookSpecificOutput`` payload for this session (``{}`` if nothing to contribute).

    Side effect: activates the default profile when none is active and a default is configured.
    """
    active = read_state(project_dir)
    if active is None and config.default_profile:
        bundle = resolve_bundle(profiles, [config.default_profile])
        activate(project_dir, vault, bundle, now=now)
        active_names = [config.default_profile]
    elif active is not None:
        active_names = list(active.get("profiles", []))
    else:
        active_names = []

    parts: list[str] = []
    if active_names:
        parts.append(f"Cairn profile(s) active in this project: {', '.join(active_names)}.")
    brief = latest_brief(vault, project_dir.name)
    if brief:
        parts.append("Latest Cairn checkpoint for this project:\n\n" + brief)

    if not parts:
        return {}
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n\n".join(parts),
        }
    }
    if active_names:
        output["hookSpecificOutput"]["reloadSkills"] = True
    return output
