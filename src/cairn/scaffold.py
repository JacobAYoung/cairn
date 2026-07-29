"""Starter config files written by ``cairn init`` — non-destructive (never overwrite existing).

The starter ships a ``default`` profile and wires ``[defaults].profile = "default"`` so the
SessionStart hook has something to auto-activate out of the box (an empty default is a valid no-op
until the user fills it in). Delegate settings are present but commented, so nothing turns on by
surprise.
"""

from __future__ import annotations

from cairn.vault import Vault


def _cairn_toml(machine: str, sync_mode: str) -> str:
    return f"""\
[machine]
name = "{machine}"

[sync]
mode = "{sync_mode}"   # off | folder | syncthing | git

[defaults]
profile = "default"   # auto-activated on session start when nothing else is active

# Uncomment to delegate bulk/mechanical work to a local model (saves tokens):
# [delegate]
# enabled  = true
# endpoint = "http://localhost:11434"
# default  = "qwen2.5:14b"
# tasks    = {{ summarize = "qwen2.5:14b", classify = "nemotron-mini" }}
"""


_PROFILES_TOML = """\
# Bundles you toggle per project. The `default` profile auto-activates on session start
# (see [defaults].profile in cairn.toml). Put skills/memories you want everywhere in `default`.

[profiles.default]
skills   = []
memories = []
# model  = "opus"

# Example of a task-specific bundle:
# [profiles.dev-heavy]
# skills   = ["develop", "audit-and-review"]
# memories = ["code-conventions"]
# model    = "opus"
"""


def write_starter_config(vault: Vault, *, machine: str, sync_mode: str) -> list[str]:
    """Write ``cairn.toml`` / ``profiles.toml`` if absent; return the filenames actually created."""
    vault.ensure_layout()
    created: list[str] = []
    if not vault.cairn_config_path.exists():
        vault.cairn_config_path.write_text(_cairn_toml(machine, sync_mode))
        created.append("cairn.toml")
    if not vault.profiles_path.exists():
        vault.profiles_path.write_text(_PROFILES_TOML)
        created.append("profiles.toml")
    return created
