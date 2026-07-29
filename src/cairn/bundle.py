"""Shareable profile bundles — ``cairn export`` / ``cairn install`` (#5.9).

A **bundle** is a self-contained directory you can push to GitHub and someone else can install:

    <bundle>/
      cairn-bundle.json     # profile definition(s) (flattened — no `extends` to chase)
      skills/<name>/...      # the skill dirs the profile references
      memories/<name>.md     # the memory files it references

Export **flattens** the profile (resolves inheritance) so the bundle stands alone. The manifest is
JSON (machine-generated) so we need no TOML *writer* dependency; install serializes the profile back
into the user's ``profiles.toml`` with a tiny value emitter and verifies via the real loader.

This module is filesystem-only (no network); the ``install`` command clones a git URL to a temp dir
and hands the path here, so the merge logic is fully unit-testable.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from cairn.activation import resolve_bundle
from cairn.config import Profile, load_profiles
from cairn.errors import CairnError
from cairn.vault import Vault

MANIFEST_NAME = "cairn-bundle.json"


@dataclass(frozen=True)
class ExportResult:
    profile: str
    skills: tuple[str, ...]
    memories: tuple[str, ...]
    dest: Path


@dataclass(frozen=True)
class InstallResult:
    skills_added: tuple[str, ...]
    memories_added: tuple[str, ...]
    profiles_added: tuple[str, ...]
    skipped: tuple[str, ...]


def export_bundle(
    vault: Vault, profiles: dict[str, Profile], name: str, dest: Path
) -> ExportResult:
    """Package ``name`` (flattened) + its skills/memories into a bundle directory at ``dest``."""
    bundle = resolve_bundle(profiles, [name])  # flatten inheritance
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "skills").mkdir(exist_ok=True)
    (dest / "memories").mkdir(exist_ok=True)

    for skill in bundle.skills:
        src = vault.skill_path(skill)  # raises if missing → nothing half-written matters
        shutil.copytree(src, dest / "skills" / skill, dirs_exist_ok=True)
    for memory in bundle.memories:
        shutil.copy2(vault.memory_path(memory), dest / "memories" / f"{memory}.md")

    manifest = {
        "profiles": {
            name: {
                "skills": list(bundle.skills),
                "memories": list(bundle.memories),
                "model": bundle.model,
                "mcp": bundle.mcp,
            }
        }
    }
    (dest / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    return ExportResult(name, bundle.skills, bundle.memories, dest)


def _toml_value(value: object) -> str:
    """Serialize a scalar/list into a TOML value (only the types profiles use)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise CairnError(f"cannot serialize bundle value of type {type(value).__name__}")


def _profile_block_toml(name: str, definition: dict) -> str:
    """Render a `[profiles.<name>]` TOML block (+ nested mcp tables) from a manifest entry."""
    lines = [
        f"[profiles.{name}]",
        f"skills = {_toml_value(definition.get('skills', []))}",
        f"memories = {_toml_value(definition.get('memories', []))}",
    ]
    if definition.get("model"):
        lines.append(f"model = {_toml_value(definition['model'])}")
    blocks = ["\n".join(lines)]
    for server, cfg in (definition.get("mcp") or {}).items():
        mcp_lines = [f"[profiles.{name}.mcp.{server}]"]
        for key, val in cfg.items():
            mcp_lines.append(f"{key} = {_toml_value(val)}")
        blocks.append("\n".join(mcp_lines))
    return "\n\n".join(blocks)


def install_bundle(vault: Vault, bundle_dir: Path) -> InstallResult:
    """Merge a bundle directory into the vault: copy assets + append profiles (skip existing)."""
    manifest_path = bundle_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise CairnError(f"not a Cairn bundle (missing {MANIFEST_NAME}): {bundle_dir}")
    manifest = json.loads(manifest_path.read_text())
    vault.ensure_layout()

    skills_added: list[str] = []
    memories_added: list[str] = []
    skipped: list[str] = []

    src_skills = bundle_dir / "skills"
    if src_skills.is_dir():
        for entry in sorted(p for p in src_skills.iterdir() if p.is_dir()):
            if (vault.skills_dir / entry.name).exists():
                skipped.append(f"skill:{entry.name}")
                continue
            shutil.copytree(entry, vault.skills_dir / entry.name)
            skills_added.append(entry.name)

    src_memories = bundle_dir / "memories"
    if src_memories.is_dir():
        for entry in sorted(src_memories.glob("*.md")):
            if (vault.memories_dir / entry.name).exists():
                skipped.append(f"memory:{entry.stem}")
                continue
            shutil.copy2(entry, vault.memories_dir / entry.name)
            memories_added.append(entry.stem)

    existing = load_profiles(vault.profiles_path)
    profiles_added: list[str] = []
    blocks: list[str] = []
    for pname, definition in manifest.get("profiles", {}).items():
        if pname in existing:
            skipped.append(f"profile:{pname}")
            continue
        blocks.append(_profile_block_toml(pname, definition))
        profiles_added.append(pname)
    if blocks:
        prefix = "\n" if vault.profiles_path.exists() else ""
        with vault.profiles_path.open("a") as handle:
            handle.write(prefix + "\n\n".join(blocks) + "\n")

    return InstallResult(
        tuple(skills_added), tuple(memories_added), tuple(profiles_added), tuple(skipped)
    )
