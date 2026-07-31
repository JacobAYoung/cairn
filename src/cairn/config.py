"""Typed configuration models and TOML loaders.

Cairn's two human-edited files are read here into small frozen dataclasses:

- ``cairn.toml``  → :class:`CairnConfig` (machine identity, sync, delegate, bridge)
- ``profiles.toml`` → a ``{name: Profile}`` map

Design notes:
- **Read-only.** Cairn never writes these files (users hand-edit them), so there is no TOML
  *writer* dependency — parsing uses stdlib ``tomllib``. State Cairn *does* write (manifest,
  per-project state) is JSON, also stdlib. Net: zero third-party deps for config.
- **Missing file → defaults**, so a fresh machine works with no config. A file that *exists* but
  is malformed or has an invalid value → :class:`ConfigError` with a specific, fixable message.
- Every loader takes its inputs as arguments (path, and ``default_machine_name``) rather than
  reaching for ``socket``/globals — keeping the logic pure and testable without a real hostname.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from cairn.errors import ConfigError

VALID_SYNC_MODES = ("folder", "syncthing", "git", "off")
DEFAULT_DELEGATE_ENDPOINT = "http://localhost:11434"
DEFAULT_BRIDGE_PORT = 8787


@dataclass(frozen=True)
class Profile:
    """A named bundle activated per project: skills + memories + an optional model.

    ``extends`` names other profiles this one inherits from (parents first, child overrides) so
    common bundles aren't copy-pasted. Inheritance is expanded in ``activation.resolve_bundle``.
    """

    name: str
    skills: tuple[str, ...] = ()
    memories: tuple[str, ...] = ()
    model: str | None = None
    delegate: bool = False
    extends: tuple[str, ...] = ()
    # server-name -> opaque MCP server config (passed through to the project's .mcp.json)
    mcp: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncConfig:
    """How the vault syncs across machines. ``path`` is required only for ``folder`` mode."""

    mode: str = "off"
    path: Path | None = None


@dataclass(frozen=True)
class DelegateConfig:
    """Local-model delegation settings (Phase 2 uses these; parsed now so config is stable)."""

    enabled: bool = False
    endpoint: str = DEFAULT_DELEGATE_ENDPOINT
    default_model: str | None = None
    tasks: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BridgeConfig:
    """Tier-1 live-bridge settings. Off by default; the only port-binding feature."""

    enabled: bool = False
    port: int = DEFAULT_BRIDGE_PORT


@dataclass(frozen=True)
class MachineConfig:
    """This machine's identity — its mailbox address. Defaults to the hostname."""

    name: str


@dataclass(frozen=True)
class CairnConfig:
    """The whole of ``cairn.toml``, with defaults filled in."""

    machine: MachineConfig
    sync: SyncConfig
    delegate: DelegateConfig
    bridge: BridgeConfig
    default_profile: str | None = None


def _read_toml(path: Path) -> dict:
    """Parse a TOML file to a dict, or raise a specific ConfigError. Missing file → ``{}``."""
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid TOML: {exc}") from exc


def _require_str_list(value: object, *, where: str) -> tuple[str, ...]:
    """Coerce a TOML value that must be a list of strings, or raise ConfigError naming ``where``."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where} must be a list of strings")
    return tuple(value)


def load_cairn_config(
    path: Path, *, default_machine_name: str, machine_override: str | None = None
) -> CairnConfig:
    """Load ``cairn.toml`` into a :class:`CairnConfig`, applying defaults and validating values.

    ``default_machine_name`` (typically the hostname) is used when ``[machine].name`` is absent.
    ``machine_override`` (typically ``$CAIRN_MACHINE``) wins over both the file and the default,
    giving each session on a shared vault its own mailbox identity. ``None`` means "not overridden".
    """
    data = _read_toml(path)

    if machine_override is not None:
        machine_name = machine_override
    else:
        machine_name = data.get("machine", {}).get("name", default_machine_name)
    if not isinstance(machine_name, str) or not machine_name:
        raise ConfigError("[machine].name must be a non-empty string")

    sync_raw = data.get("sync", {})
    mode = sync_raw.get("mode", "off")
    if mode not in VALID_SYNC_MODES:
        raise ConfigError(
            f"[sync].mode must be one of {', '.join(VALID_SYNC_MODES)}; got {mode!r}"
        )
    # `path` is optional and reserved: with folder/syncthing the vault root itself is what an
    # external tool syncs, so no separate path is needed. Parsed (and ~-expanded) if present.
    raw_path = sync_raw.get("path")
    sync_path = Path(raw_path).expanduser() if isinstance(raw_path, str) else None

    delegate_raw = data.get("delegate", {})
    tasks = delegate_raw.get("tasks", {})
    if not isinstance(tasks, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in tasks.items()
    ):
        raise ConfigError("[delegate].tasks must be a table of string -> string")

    bridge_raw = data.get("bridge", {})
    port = bridge_raw.get("port", DEFAULT_BRIDGE_PORT)
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise ConfigError("[bridge].port must be an integer between 1 and 65535")

    default_profile = data.get("defaults", {}).get("profile")
    if default_profile is not None and not isinstance(default_profile, str):
        raise ConfigError("[defaults].profile must be a string")

    return CairnConfig(
        machine=MachineConfig(name=machine_name),
        sync=SyncConfig(mode=mode, path=sync_path),
        delegate=DelegateConfig(
            enabled=bool(delegate_raw.get("enabled", False)),
            endpoint=delegate_raw.get("endpoint", DEFAULT_DELEGATE_ENDPOINT),
            default_model=delegate_raw.get("default"),
            tasks=dict(tasks),
        ),
        bridge=BridgeConfig(enabled=bool(bridge_raw.get("enabled", False)), port=port),
        default_profile=default_profile,
    )


def load_profiles(path: Path) -> dict[str, Profile]:
    """Load ``profiles.toml`` into a ``{name: Profile}`` map. Missing file → ``{}``."""
    data = _read_toml(path)
    profiles_raw = data.get("profiles", {})
    if not isinstance(profiles_raw, dict):
        raise ConfigError("[profiles] must be a table of named profiles")

    profiles: dict[str, Profile] = {}
    for name, body in profiles_raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"profile {name!r} must be a table")
        model = body.get("model")
        if model is not None and not isinstance(model, str):
            raise ConfigError(f"profile {name!r}: model must be a string")
        raw_extends = body.get("extends", [])
        if isinstance(raw_extends, str):
            raw_extends = [raw_extends]
        mcp = body.get("mcp", {})
        if not isinstance(mcp, dict) or not all(isinstance(v, dict) for v in mcp.values()):
            raise ConfigError(f"profile {name!r}: mcp must be a table of server-name -> config")
        profiles[name] = Profile(
            name=name,
            skills=_require_str_list(body.get("skills", []), where=f"profile {name!r}: skills"),
            memories=_require_str_list(
                body.get("memories", []), where=f"profile {name!r}: memories"
            ),
            model=model,
            delegate=bool(body.get("delegate", False)),
            extends=_require_str_list(raw_extends, where=f"profile {name!r}: extends"),
            mcp={k: dict(v) for k, v in mcp.items()},
        )
    return profiles
