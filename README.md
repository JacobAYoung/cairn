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

## Install & set up

Two one-time commands per machine:

```bash
pipx install cairn     # once published
cairn init             # scaffold the vault, import your ~/.claude skills/memories,
                       # install the Cairn skill + a SessionStart hook into ~/.claude
```

After that, edit the `default` profile in `~/.cairn/profiles.toml`. From then on it's automatic:
every Claude session runs the hook, which auto-activates your default profile and loads your latest
warm-start note — no per-session commands. Switch setups per project with `cairn use <profile>`.

**Vault on a shared drive or git repo (single user, one or many machines):** point `CAIRN_HOME` at a
synced/network folder with `[sync].mode = "folder"`, or use `[sync].mode = "git"` for a git-repo vault.

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

## How it integrates with Claude (and, later, other agents)

Cairn needs **no plugin, API, or MCP server**. It integrates at two levels, both native:

1. **Setup-time:** `cairn use` writes into the files Claude Code already reads at session start —
   `.claude/skills/`, `.claude/rules/`, `.claude/settings.local.json`. Activation *is* the integration.
2. **Runtime:** it's a plain CLI on your `PATH`, so Claude can call `cairn use`/`ask`/`checkpoint`
   directly. A bundled Cairn skill (planned) teaches Claude *when* to reach for those commands.

**Model-agnostic by design:** everything except the activation *target* is already agent-neutral —
the vault, profiles, sync, mailbox, warm-start, and `cairn ask` (which talks to any local model). A
future `AgentAdapter` seam (BACKLOG #5.11) lets other agents become activation targets. Focus is
Claude for now.

## Design principles

No admin ever for core features · minimal dependencies · one human-editable TOML config ·
CLI-first · drivable by Claude itself · reversible and non-destructive. See
[CLAUDE.md](CLAUDE.md) for the full engineering standard every change must meet.
