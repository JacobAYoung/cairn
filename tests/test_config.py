"""Tests for the config layer (:mod:`cairn.config`).

These assert the exact parsed DATA (every field, with defaults filled) and the exact failure
behavior (which invalid input raises :class:`ConfigError`, and that a *missing* file yields
defaults rather than an error). Malformed values must fail loud with a fixable message; absent
optional sections must fall back to documented defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.config import (
    DEFAULT_BRIDGE_PORT,
    DEFAULT_DELEGATE_ENDPOINT,
    load_cairn_config,
    load_profiles,
)
from cairn.errors import ConfigError


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


# --- cairn.toml ---------------------------------------------------------------------------


def test_full_cairn_config_parses_every_field(tmp_path):
    # Arrange
    path = _write(
        tmp_path / "cairn.toml",
        """
        [machine]
        name = "desktop"

        [sync]
        mode = "folder"
        path = "~/Sync/cairn"

        [delegate]
        enabled = true
        endpoint = "http://mac-mini.local:11434"
        default = "qwen2.5:14b"
        tasks = { summarize = "qwen2.5:14b", classify = "nemotron-mini" }

        [bridge]
        enabled = true
        port = 9001
        """,
    )

    # Act
    config = load_cairn_config(path, default_machine_name="fallback")

    # Assert OUTPUT: exact values, defaults overridden, ~ expanded
    assert config.machine.name == "desktop"
    assert config.sync.mode == "folder"
    assert config.sync.path == Path("~/Sync/cairn").expanduser()
    assert config.delegate.enabled is True
    assert config.delegate.endpoint == "http://mac-mini.local:11434"
    assert config.delegate.default_model == "qwen2.5:14b"
    assert config.delegate.tasks == {"summarize": "qwen2.5:14b", "classify": "nemotron-mini"}
    assert config.bridge.enabled is True
    assert config.bridge.port == 9001


def test_missing_file_yields_documented_defaults(tmp_path):
    # Act: no file on disk
    config = load_cairn_config(tmp_path / "cairn.toml", default_machine_name="my-host")

    # Assert: defaults, machine name falls back to the injected hostname
    assert config.machine.name == "my-host"
    assert config.sync == type(config.sync)(mode="off", path=None)
    assert config.delegate.enabled is False
    assert config.delegate.endpoint == DEFAULT_DELEGATE_ENDPOINT
    assert config.delegate.tasks == {}
    assert config.bridge.enabled is False
    assert config.bridge.port == DEFAULT_BRIDGE_PORT


def test_invalid_sync_mode_raises(tmp_path):
    path = _write(tmp_path / "cairn.toml", '[sync]\nmode = "rsync"\n')
    with pytest.raises(ConfigError, match="sync..mode"):
        load_cairn_config(path, default_machine_name="h")


def test_folder_mode_without_path_raises(tmp_path):
    path = _write(tmp_path / "cairn.toml", '[sync]\nmode = "folder"\n')
    with pytest.raises(ConfigError, match="path is required"):
        load_cairn_config(path, default_machine_name="h")


def test_out_of_range_port_raises(tmp_path):
    path = _write(tmp_path / "cairn.toml", "[bridge]\nport = 70000\n")
    with pytest.raises(ConfigError, match="port"):
        load_cairn_config(path, default_machine_name="h")


def test_malformed_toml_raises_with_filename(tmp_path):
    path = _write(tmp_path / "cairn.toml", "[machine\nname = oops")
    with pytest.raises(ConfigError, match="cairn.toml is not valid TOML"):
        load_cairn_config(path, default_machine_name="h")


# --- profiles.toml ------------------------------------------------------------------------


def test_profiles_parse_with_fields_and_defaults(tmp_path):
    # Arrange: one fully-specified profile, one minimal (exercises defaults)
    path = _write(
        tmp_path / "profiles.toml",
        """
        [profiles.dev-heavy]
        skills   = ["develop", "audit-and-review"]
        memories = ["code-conventions"]
        model    = "opus"
        delegate = true

        [profiles.research]
        skills = ["web-notes"]
        """,
    )

    # Act
    profiles = load_profiles(path)

    # Assert OUTPUT: both profiles, exact bundle contents, name injected, defaults applied
    assert set(profiles) == {"dev-heavy", "research"}
    dev = profiles["dev-heavy"]
    assert dev.name == "dev-heavy"
    assert dev.skills == ("develop", "audit-and-review")
    assert dev.memories == ("code-conventions",)
    assert dev.model == "opus"
    assert dev.delegate is True

    research = profiles["research"]
    assert research.skills == ("web-notes",)
    assert research.memories == ()  # default
    assert research.model is None  # default
    assert research.delegate is False  # default


def test_missing_profiles_file_is_empty_map(tmp_path):
    assert load_profiles(tmp_path / "profiles.toml") == {}


def test_profile_with_non_list_skills_raises(tmp_path):
    path = _write(tmp_path / "profiles.toml", '[profiles.bad]\nskills = "develop"\n')
    with pytest.raises(ConfigError, match="skills must be a list of strings"):
        load_profiles(path)


def test_profile_with_non_string_model_raises(tmp_path):
    path = _write(tmp_path / "profiles.toml", "[profiles.bad]\nmodel = 5\n")
    with pytest.raises(ConfigError, match="model must be a string"):
        load_profiles(path)
