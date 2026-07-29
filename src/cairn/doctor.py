"""Health checks for ``cairn doctor`` — catch the things that silently break the "just works" flow.

Pure-ish: :func:`run_checks` takes the vault + project dir (and an injectable ``ping`` for the
delegate endpoint) and returns a list of :class:`Check`. The command layer renders them and derives
the exit code. Checks are ordered from foundational (vault/config) to operational (links/sync).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cairn.config import load_cairn_config, load_profiles
from cairn.errors import ConfigError
from cairn.sync import make_sync_backend
from cairn.system import default_machine_name
from cairn.vault import Vault

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass(frozen=True)
class Check:
    """One diagnostic result."""

    name: str
    status: str  # OK | WARN | FAIL
    detail: str


def _default_ping(endpoint: str) -> bool:
    """Best-effort reachability probe of an Ollama endpoint (never raises)."""
    import httpx

    try:
        return httpx.get(endpoint.rstrip("/") + "/api/tags", timeout=2).status_code < 500
    except Exception:
        return False


def _dangling_links(project_dir: Path) -> list[str]:
    """Cairn-style symlinks under .claude that no longer resolve (e.g. vault not mounted)."""
    broken: list[str] = []
    for sub in ("skills", "rules"):
        directory = project_dir / ".claude" / sub
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if path.is_symlink() and not path.exists():
                    broken.append(str(path.relative_to(project_dir)))
    return broken


def run_checks(vault: Vault, project_dir: Path, *, ping=_default_ping) -> list[Check]:
    """Run all diagnostics and return them in display order."""
    checks: list[Check] = []

    checks.append(
        Check("vault", OK if vault.exists() else WARN, str(vault.root))
        if vault.exists()
        else Check("vault", WARN, f"{vault.root} (missing — run `cairn init`)")
    )

    config = None
    try:
        config = load_cairn_config(
            vault.cairn_config_path, default_machine_name=default_machine_name()
        )
        checks.append(Check("config", OK, "cairn.toml valid"))
    except ConfigError as exc:
        checks.append(Check("config", FAIL, str(exc)))

    try:
        profiles = load_profiles(vault.profiles_path)
        checks.append(Check("profiles", OK, f"{len(profiles)} profile(s)"))
        if config and config.default_profile:
            if config.default_profile in profiles:
                checks.append(Check("default-profile", OK, config.default_profile))
            else:
                missing = config.default_profile
                checks.append(Check("default-profile", FAIL, f"'{missing}' not in profiles.toml"))
    except ConfigError as exc:
        checks.append(Check("profiles", FAIL, str(exc)))

    broken = _dangling_links(project_dir)
    checks.append(
        Check("links", FAIL, f"{len(broken)} dangling: {', '.join(broken)}")
        if broken
        else Check("links", OK, "no dangling links")
    )

    if config:
        status = make_sync_backend(config.sync.mode, vault.root).status()
        checks.append(Check("sync", OK if status.ok else WARN, f"{status.mode} — {status.detail}"))
        if config.delegate.enabled:
            reachable = ping(config.delegate.endpoint)
            checks.append(
                Check(
                    "delegate",
                    OK if reachable else WARN,
                    config.delegate.endpoint + (" reachable" if reachable else " unreachable"),
                )
            )

    return checks
