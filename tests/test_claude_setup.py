"""Tests for wiring Cairn into a Claude Code install (:mod:`cairn.claude_setup`).

Both installers must be non-destructive and idempotent, so these assert on-disk results against a
temp ``.claude`` dir and that a rerun preserves everything and adds nothing.
"""

from __future__ import annotations

import json

from cairn.claude_setup import HOOK_COMMAND, install_session_start_hook, install_skill


def test_install_skill_copies_bundled_skill(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    dest = install_skill(skills_dir)

    assert dest == skills_dir / "cairn"
    content = (dest / "SKILL.md").read_text()
    assert "name: cairn" in content  # the bundled skill's frontmatter


def test_install_hook_adds_entry_and_is_idempotent(tmp_path):
    settings_path = tmp_path / "settings.json"

    # First install into an empty config -> added
    assert install_session_start_hook(settings_path) is True
    settings = json.loads(settings_path.read_text())
    commands = [
        h["command"]
        for entry in settings["hooks"]["SessionStart"]
        for h in entry["hooks"]
    ]
    assert commands == [HOOK_COMMAND]

    # Second install -> no-op, still exactly one entry
    assert install_session_start_hook(settings_path) is False
    settings = json.loads(settings_path.read_text())
    assert len(settings["hooks"]["SessionStart"]) == 1


def test_install_hook_preserves_existing_settings_and_hooks(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "model": "opus",
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}
                    ]
                },
            }
        )
    )

    install_session_start_hook(settings_path)

    settings = json.loads(settings_path.read_text())
    # unrelated setting + unrelated hook survive; our hook is added alongside
    assert settings["model"] == "opus"
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "x"
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == HOOK_COMMAND
