# Cairn

**Portable, toggleable, cross-machine vault for your Claude Code setup.**

Cairn is a small CLI + one TOML config file that turns Claude Code's scattered primitives —
skills, per-scope settings, per-subagent model choice, `~/.claude` — into named bundles you can
**toggle per project** and that **follow you across machines**. It also offloads cheap bulk work to
local models (free tokens) and keeps warm-start notes so new sessions skip expensive re-exploration.

- **Design:** [SPEC.md](SPEC.md)
- **Roadmap & goals:** [BACKLOG.md](BACKLOG.md)
- **Engineering standards (enforced):** [CLAUDE.md](CLAUDE.md)

## Quickstart

**Requires:** Python 3.11+ and [`pipx`](https://pipx.pypa.io) (`brew install pipx` on macOS). A local
[Ollama](https://ollama.com) is optional (only for `cairn ask` delegation).

```bash
pipx install git+https://github.com/JacobAYoung/cairn.git
cairn init      # scaffold the vault (~/.cairn), import your ~/.claude skills/memories,
                # install the Cairn skill + a SessionStart hook into ~/.claude
```

Then open `~/.cairn/profiles.toml` and list the skills/memories you want everywhere in the `default`
profile. That's it — from now on **every Claude Code session auto-loads your default bundle** (via the
hook `init` installed) with no commands to run. Switch setups per project with `cairn use <profile>`,
and check health anytime with `cairn doctor`.

> `cairn` must be on your PATH so the hook can find it — pipx handles this; verify with `which cairn`.
> To update later: `pipx install --force git+https://github.com/JacobAYoung/cairn.git`.

## Share one vault across your machines

The vault is just a folder (`~/.cairn`), so point it at anything that syncs:

- **Cloud folder (simplest):** `cairn init --vault-path ~/Dropbox/cairn --sync folder` (or iCloud/OneDrive).
  Dropbox/iCloud does the syncing; Cairn just lives there. On the second machine run the same command
  with the same path — your skills, memories, and profiles are already there.
- **Syncthing (no cloud):** put `~/.cairn` in a Syncthing-shared folder and set `[sync].mode = "syncthing"`.
- **Git repo:** `cairn init --vault-path ~/cairn-vault --sync git`, then `git init` + add a remote in
  that folder; `cairn` wraps pull/commit/push in the background.

`--vault-path` is remembered in `~/.config/cairn/location`, so you set it once per machine.

## Develop

Requires Python 3.11+ (for stdlib `tomllib`).

```bash
git clone https://github.com/JacobAYoung/cairn.git && cd cairn
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
   directly. A bundled Cairn skill (installed by `cairn init`) teaches Claude *when* to reach for them.

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
| `cairn handoff <machine>` · `cairn resume` | Carry active profile + latest brief to another machine |
| `cairn export <profile> <dir>` · `cairn install <url\|dir>` | Share a profile bundle (e.g. via GitHub) |
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

[profiles.research]
skills = ["web-notes"]
[profiles.research.mcp.brave]   # MCP servers activate into the project's .mcp.json
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-brave-search"]
```

## Share a profile with a friend

A profile (its skills + memories + model + MCP servers) travels as a self-contained bundle:

```bash
cairn export dev-heavy ./dev-heavy-bundle   # then push that dir to a GitHub repo
# your friend:
cairn install https://github.com/you/dev-heavy-bundle
```

`install` also takes a local directory, and skips anything already in your vault (never clobbers).

## Design principles

No admin ever for core features · minimal dependencies (only `httpx`) · one human-editable TOML
config · CLI-first · drivable by Claude itself · reversible and non-destructive · **files are the
source of truth** (no opaque database). See [CLAUDE.md](CLAUDE.md) for the full engineering standard
every change must meet, and [SPEC.md](SPEC.md) for design + positioning.
