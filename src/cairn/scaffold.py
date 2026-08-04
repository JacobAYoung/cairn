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

# Delegation workers — cheaper models the driver hands sub-tasks to, to save budget.
# `claude` workers become subagents in ~/.claude/agents (the driver delegates via the Task tool);
# `local` workers run on Ollama over HTTP (`cairn workers run <name> "..."`). Adding one is pure
# config — run `cairn workers sync` after editing. See docs/DELEGATION.md.
[[worker]]
name    = "delegate"
backend = "claude"
model   = "sonnet"
role    = "Well-scoped sub-tasks: search many files, summarize/extract, draft, multi-file edits."

[[worker]]
name    = "delegate-fast"
backend = "claude"
model   = "haiku"
role    = "Rote bulk work: formatting, extraction, bulk edits, collation, simple classification."

# Example local (Ollama) worker — uncomment once Ollama is running with the model pulled:
# [[worker]]
# name     = "summarizer"
# backend  = "local"
# model    = "qwen2.5:14b"
# endpoint = "http://localhost:11434"
# role     = "Summarize/extract from large text, off-API and free."
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
