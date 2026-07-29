# Cairn

**Portable, toggleable, cross-machine vault for your Claude Code setup.**

Cairn is a small CLI + one TOML config file that turns Claude Code's scattered primitives —
skills, per-scope settings, per-subagent model choice, `~/.claude` — into named bundles you can
**toggle per project** and that **follow you across machines**. It also offloads cheap bulk work to
local models (free tokens) and keeps warm-start notes so new sessions skip expensive re-exploration.

- **Design:** [SPEC.md](SPEC.md)
- **Roadmap & goals:** [BACKLOG.md](BACKLOG.md)
- **Engineering standards (enforced):** [CLAUDE.md](CLAUDE.md)

> Status: **early scaffolding.** The CLI dispatch layer and packaging are in place; real
> subcommands (`use`, `status`, `ask`, …) are landing per the backlog.

## Install

End users (once published):

```bash
pipx install cairn
```

## Develop

Requires Python 3.11+ (for stdlib `tomllib`).

```bash
git clone <repo> && cd cairn
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest          # run the test suite
ruff check .    # lint
cairn --version # smoke-test the entry point
```

## Design principles

No admin ever for core features · minimal dependencies · one human-editable TOML config ·
CLI-first · drivable by Claude itself · reversible and non-destructive. See
[CLAUDE.md](CLAUDE.md) for the full engineering standard every change must meet.
