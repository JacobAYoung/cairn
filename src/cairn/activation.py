"""Profile activation — the heart of ``cairn use`` / ``cairn clear`` (SPEC Appendix A).

Split into a **pure resolver** (:func:`resolve_bundle`, no I/O — trivially testable) and the
**filesystem effect** (:func:`activate` / :func:`deactivate`). The invariants that make this safe
to run against a real project:

- **All-or-nothing validation.** Unknown profile or a skill/memory missing from the vault raises
  *before* any file is touched — no half-applied state.
- **Cairn only ever removes what it created.** Every symlink is recorded in
  ``<project>/.cairn/manifest.json``; ``deactivate`` reverses exactly that list and restores the
  prior ``model`` value. A hand-placed file with the same name is never clobbered or removed.
- **Only the file we change is backed up** — ``.claude/settings.local.json`` — not the whole tree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cairn.config import Profile
from cairn.errors import CairnError
from cairn.vault import Vault

MANIFEST_NAME = "manifest.json"
STATE_NAME = "state.json"


@dataclass(frozen=True)
class Bundle:
    """The merged result of one or more profiles: what to link and which model to set."""

    profiles: tuple[str, ...]
    skills: tuple[str, ...]
    memories: tuple[str, ...]
    model: str | None


@dataclass(frozen=True)
class ActivationResult:
    """What :func:`activate` did — returned for reporting and asserted in tests."""

    profiles: tuple[str, ...]
    linked_skills: tuple[str, ...]
    linked_memories: tuple[str, ...]
    model: str | None


def _dedupe(items: tuple[str, ...]) -> tuple[str, ...]:
    """Order-preserving de-duplication (so merged bundles are stable and predictable)."""
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return tuple(seen)


def resolve_bundle(profiles: dict[str, Profile], names: list[str]) -> Bundle:
    """Merge the named profiles into one :class:`Bundle` (pure).

    Skills/memories are unioned in first-seen order; ``model`` is the last specified one (so a
    later profile in ``a,b`` overrides an earlier model). An unknown name raises before any caller
    touches the filesystem.
    """
    if not names:
        raise CairnError("no profile given")
    unknown = [n for n in names if n not in profiles]
    if unknown:
        available = ", ".join(sorted(profiles)) or "(none)"
        raise CairnError(f"unknown profile(s): {', '.join(unknown)}. Available: {available}")

    skills: tuple[str, ...] = ()
    memories: tuple[str, ...] = ()
    model: str | None = None
    for name in names:
        profile = profiles[name]
        skills += profile.skills
        memories += profile.memories
        if profile.model is not None:
            model = profile.model
    return Bundle(tuple(names), _dedupe(skills), _dedupe(memories), model)


def _cairn_dir(project_dir: Path) -> Path:
    return project_dir / ".cairn"


def _link(target: Path, link_path: Path) -> None:
    """Create ``link_path`` -> ``target``, refusing to clobber an existing non-Cairn path."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists() or link_path.is_symlink():
        # Only tolerate a link we'd have made ourselves; never remove a real file/dir.
        if link_path.is_symlink() and link_path.resolve() == target.resolve():
            return
        raise CairnError(f"refusing to overwrite existing {link_path}")
    link_path.symlink_to(target)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _ensure_gitignored(project_dir: Path, entry: str = ".cairn/") -> None:
    """Add ``entry`` to the project's .gitignore if one exists and doesn't already list it."""
    gitignore = project_dir / ".gitignore"
    if not gitignore.exists():
        return
    lines = gitignore.read_text().splitlines()
    if entry not in lines:
        gitignore.write_text(gitignore.read_text().rstrip("\n") + f"\n{entry}\n")


def activate(project_dir: Path, vault: Vault, bundle: Bundle, *, now: str) -> ActivationResult:
    """Apply ``bundle`` to ``project_dir``: symlink skills/memories, merge model, record a manifest.

    Re-activating replaces any prior Cairn state (a preceding :func:`deactivate` is run). Validates
    every vault path first, so a bad bundle changes nothing.
    """
    # 1. Validate all referenced skills/memories exist — raises before any change.
    skill_targets = {name: vault.skill_path(name) for name in bundle.skills}
    memory_targets = {name: vault.memory_path(name) for name in bundle.memories}

    # 2. Clear any prior activation so links/model don't accumulate.
    if (_cairn_dir(project_dir) / MANIFEST_NAME).exists():
        deactivate(project_dir)

    claude = project_dir / ".claude"
    cairn = _cairn_dir(project_dir)
    (cairn / "backup").mkdir(parents=True, exist_ok=True)

    links: list[str] = []

    # 3. Link skills -> .claude/skills/<name>, memories -> .claude/rules/<name>.md
    for name, target in skill_targets.items():
        link_path = claude / "skills" / name
        _link(target, link_path)
        links.append(str(link_path.relative_to(project_dir)))
    for name, target in memory_targets.items():
        link_path = claude / "rules" / f"{name}.md"
        _link(target, link_path)
        links.append(str(link_path.relative_to(project_dir)))

    # 4. Merge model into settings.local.json, backing up the prior value.
    settings_path = claude / "settings.local.json"
    prior_settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    prior_had_model = "model" in prior_settings
    prior_model = prior_settings.get("model")
    model_written = bundle.model is not None
    if model_written:
        (cairn / "backup" / "settings.local.json").write_text(
            json.dumps(prior_settings, indent=2) + "\n"
        )
        merged = {**prior_settings, "model": bundle.model}
        _write_json(settings_path, merged)

    # 5. Manifest (reversal source of truth) + human-facing state.
    _write_json(
        cairn / MANIFEST_NAME,
        {
            "links": links,
            "model_written": model_written,
            "prior_had_model": prior_had_model,
            "prior_model": prior_model,
        },
    )
    _write_json(
        cairn / STATE_NAME,
        {"profiles": list(bundle.profiles), "activated_at": now},
    )
    _ensure_gitignored(project_dir)

    return ActivationResult(
        profiles=bundle.profiles,
        linked_skills=bundle.skills,
        linked_memories=bundle.memories,
        model=bundle.model,
    )


def deactivate(project_dir: Path) -> tuple[str, ...]:
    """Reverse a prior activation using the manifest. Returns the profiles that were active.

    Removes only Cairn-created symlinks, restores the prior ``model`` value, and clears Cairn's
    state files. Idempotent: no manifest → nothing to do.
    """
    cairn = _cairn_dir(project_dir)
    manifest_path = cairn / MANIFEST_NAME
    if not manifest_path.exists():
        return ()

    manifest = json.loads(manifest_path.read_text())

    # Remove only links we created and that still point where we left them.
    for rel in manifest.get("links", []):
        link_path = project_dir / rel
        if link_path.is_symlink():
            link_path.unlink()

    # Restore the model key to its pre-activation state.
    if manifest.get("model_written"):
        settings_path = project_dir / ".claude" / "settings.local.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            if manifest.get("prior_had_model"):
                settings["model"] = manifest.get("prior_model")
            else:
                settings.pop("model", None)
            _write_json(settings_path, settings)

    state_path = cairn / STATE_NAME
    profiles = ()
    if state_path.exists():
        profiles = tuple(json.loads(state_path.read_text()).get("profiles", []))
        state_path.unlink()
    manifest_path.unlink()
    return profiles


def read_state(project_dir: Path) -> dict | None:
    """Return the active-state dict (``{profiles, activated_at}``) for this project, or None."""
    state_path = _cairn_dir(project_dir) / STATE_NAME
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text())
