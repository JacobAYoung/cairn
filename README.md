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

## Commands

| Command | What it does |
|---|---|
| `cairn init` | One-time setup: scaffold vault, import `~/.claude` skills/memories, install skill + hook |
| `cairn ls [skills\|memories\|profiles]` | List what's in the vault |
| `cairn use <profile[,profile]> [--dry-run]` | Activate bundle(s) in the current project (persists) |
| `cairn clear` | Deactivate — remove only Cairn's links, restore the prior model |
| `cairn status` | Active profile(s) + machine / vault / sync summary |
| `cairn doctor` | Diagnose vault / config / links / sync / delegate health |
| `cairn ask <task> "<prompt>"` | Delegate a bulk subtask to a local model (free tokens) |
| `cairn checkpoint [-m ...]` | Save a warm-start note (from `-m` or stdin) |
| `cairn brief` | Print the latest warm-start note |
| `cairn recall "<query>"` | Full-text search across memories + warm-start notes |
| `cairn sync-memory [--off]` | Point Claude's auto-memory at the synced vault |
| `cairn send <machine> "<msg>"` · `cairn inbox [--read]` | Cross-machine messages (Tier-0) |
| `cairn session-start` | Internal SessionStart hook target (auto-activates default + injects brief) |

## Configuration

`~/.cairn/cairn.toml`:

```toml
[machine]
name = "desktop"            # this machine's mailbox address (default: hostname)

[sync]
mode = "syncthing"          # off | folder | syncthing | git

[defaults]
profile = "default"         # auto-activated on session start when nothing else is active

[delegate]
enabled  = true
endpoint = "http://localhost:11434"
default  = "qwen2.5:14b"
tasks    = { summarize = "qwen2.5:14b", classify = "nemotron-mini" }
```

`~/.cairn/profiles.toml`:

```toml
[profiles.base]
skills   = ["develop"]
memories = ["code-conventions"]

[profiles.dev-heavy]
extends  = ["base"]              # inherit base's skills/memories; add/override below
skills   = ["audit-and-review"]
model    = "opus"
delegate = true
```

## Recipes

**Vault on a network / shared drive (no git dance):**
```bash
cairn init --vault-path /Volumes/team-share/cairn --sync folder
```
The location is remembered (`~/.config/cairn/location`); the drive's own sync carries it between machines.

**Vault as a git repo:**
```bash
cairn init --vault-path ~/cairn-vault --sync git   # then `git init` + add a remote in that dir
```
`cairn` wraps pull/commit/push; run any command and sync is best-effort in the background.

**Second machine:** `pipx install cairn && cairn init --vault-path <same synced path>`.

## Design principles

No admin ever for core features · minimal dependencies (only `httpx`) · one human-editable TOML
config · CLI-first · drivable by Claude itself · reversible and non-destructive · **files are the
source of truth** (no opaque database). See [CLAUDE.md](CLAUDE.md) for the full engineering standard
every change must meet, and [SPEC.md](SPEC.md) for design + positioning.
