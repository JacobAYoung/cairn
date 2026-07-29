"""`cairn handoff` / `cairn resume` — the headline cross-machine flow (SPEC Pillar 5).

Handoff packages *what you'd otherwise re-explain on the other machine*: the project, the profile(s)
you had active, your latest warm-start brief, and an optional note — into a single mailbox message.
``resume`` on the other machine surfaces the newest one. Because the vault is shared, the profiles
and checkpoint are already present there; the handoff just says "pick up here."

Pure payload helpers live here (easily tested); the commands wire them to the mailbox.
"""

from __future__ import annotations

from cairn.mailbox import Message

MARKER = "### CAIRN HANDOFF"


def build_handoff_payload(
    project: str, profiles: list[str], message: str | None, brief: str | None
) -> str:
    """Compose the handoff message body: a marker + metadata + the latest brief."""
    lines = [
        MARKER,
        f"project: {project}",
        f"profiles: {', '.join(profiles) or '(none)'}",
    ]
    if message:
        lines.append(f"note: {message}")
    lines.append("")
    lines.append(brief or "(no checkpoint saved)")
    return "\n".join(lines)


def is_handoff(body: str) -> bool:
    return body.lstrip().startswith(MARKER)


def latest_handoff(messages: list[Message]) -> Message | None:
    """The newest handoff in an already-newest-first inbox, or None."""
    for message in messages:
        if is_handoff(message.body):
            return message
    return None
