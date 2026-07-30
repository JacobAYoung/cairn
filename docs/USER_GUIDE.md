# Cairn — User Guide

How to use and customize every feature. For the big picture see the [README](../README.md); for how
the code is put together see [ARCHITECTURE.md](ARCHITECTURE.md).

## Concepts in 30 seconds

- **Vault** (`~/.cairn/`) — the one place your skills and memories live, as plain files.
- **Profile** — a named bundle of skills + memories + a model + MCP servers you can turn on per project.
- **Activation** — turning a profile on in a project creates symlinks from the project's `.claude/`
  into the vault. Turning it off removes exactly those. Your files are never copied or duplicated.
- **Vault location** — `~/.cairn` by default; can live on a shared/synced folder or git repo.

Everything below assumes you've run `cairn init` once (see the README Quickstart).

---

## The vault

`cairn init` creates:

```
~/.cairn/
  skills/         one folder per skill (a Claude skill = a dir with SKILL.md)
  memories/       one <name>.md per memory (plain markdown)
  session-notes/  warm-start checkpoints
  mailbox/        cross-machine messages
  cairn.toml      global config
  profiles.toml   your bundles
```

**Add content:**
- `cairn import --skills <dir> --memories <dir>` copies existing skills/memories in (skips duplicates).
- Or just drop a folder into `~/.cairn/skills/` or a `<name>.md` into `~/.cairn/memories/` by hand.

**See what's there:** `cairn ls` (or `cairn ls skills` / `memories` / `profiles`).

---

## Profiles

Defined in `~/.cairn/profiles.toml`. A profile can set any of:

| Key | Meaning |
|---|---|
| `skills` | skill folder names from the vault |
| `memories` | memory names (the `.md` stem) from the vault |
| `model` | the Claude model to run as (written to `.claude/settings.local.json`) |
| `delegate` | `true` to opt this project into local-model delegation |
| `extends` | inherit from other profile(s) — parents first, this profile overrides |
| `[profiles.X.mcp.<server>]` | MCP servers to add to the project's `.mcp.json` |

**Example:**
```toml
[profiles.base]
skills   = ["develop"]
memories = ["code-conventions"]

[profiles.dev]
extends  = ["base"]                 # gets develop + code-conventions
skills   = ["audit-and-review"]     # …plus this
model    = "opus"

[profiles.dev.mcp.brave]            # …plus a Brave-search MCP server
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-brave-search"]
```

**Use one:** in a project, `cairn use dev` (or `cairn use dev,research` to merge several). It persists
across sessions. Preview without changing anything: `cairn use dev --dry-run`.

**Turn it off:** `cairn clear` — removes only what Cairn added and restores the prior model.

**See what's active:** `cairn status`.

---

## Auto-activation (the default profile)

`cairn init` installs a `SessionStart` hook and sets `[defaults].profile = "default"` in `cairn.toml`.
On every Claude session, the hook activates that profile (if nothing else is active) and injects your
latest warm-start note — so a project is configured with zero commands.

**Customize:** put your always-on skills/memories in `[profiles.default]`, or point
`[defaults].profile` at a different profile. Keep `default` universal; make project-specific profiles
for anything you don't want everywhere, and switch to them with `cairn use` in that project.

---

## Token optimizer

### Local-model delegation — `cairn ask`
Offload cheap, bulk, mechanical work (summarize / classify / extract / draft) to a local Ollama model
so it costs no API tokens. Claude stays the driver and calls out only when it helps.

```toml
# cairn.toml
[delegate]
enabled  = true
endpoint = "http://localhost:11434"     # or a Mac on your LAN, e.g. http://mac-mini.local:11434
default  = "qwen2.5:14b"
tasks    = { summarize = "qwen2.5:14b", classify = "nemotron-mini" }
```
```bash
cairn ask summarize "…long text…"     # prints the local model's output
```
If the endpoint is unreachable it exits non-zero with "run this task inline instead" so Claude falls
back gracefully. Delegation is for **cost on bulk work**, not latency-sensitive single questions.

### Warm-start — `cairn checkpoint` / `cairn brief`
Save a short brief at the end of a session; the next session (on any machine) loads it and skips
re-discovering everything.

```bash
cairn checkpoint -m "Decided X; next: Y; files live in Z."   # or pipe text on stdin
cairn brief                                                   # print the latest note
```
Notes are stored newest-first per project in `~/.cairn/session-notes/<project>.md`. The auto-activation
hook injects the latest one automatically, so you usually don't run `brief` by hand.

---

## Cross-machine

### One synced vault
Point the vault at something that syncs (see the README "Share one vault across your machines"):
`cairn init --vault-path ~/Dropbox/cairn --sync folder`, a Syncthing folder, or `--sync git`.

### Synced auto-memory — `cairn sync-memory`
Claude's *own* accumulated memory is machine-local by default. Redirect it into the synced vault so it
follows you: `cairn sync-memory` (undo with `cairn sync-memory --off`).

### Messages — `cairn send` / `cairn inbox`
```bash
cairn send laptop "context: the API refactor is on branch feat/x"
cairn inbox              # on the laptop; add --read to mark them read
```

### Handoff — `cairn handoff` / `cairn resume`
Package the current project's active profile + latest brief + a note for another machine:
```bash
cairn handoff laptop -m "continue the refactor"    # on the desktop
cairn resume                                        # on the laptop — shows it
```

---

## Recall — full-text search

Search across all your memories and warm-start notes (SQLite full-text, ranked, with snippets):
```bash
cairn recall "postgres"
cairn recall "composition over inheritance" --limit 5
```

---

## Doctor — health check

```bash
cairn doctor
```
Checks the vault, config validity, profiles, that `[defaults].profile` exists, dangling symlinks
(e.g. an unmounted vault), sync state, and delegate reachability. Exits non-zero if something's broken.

---

## Sharing profiles

Package a profile (flattened, with its skills/memories/MCP) and hand it to someone via GitHub:
```bash
cairn export dev ./dev-bundle          # writes a self-contained bundle dir
# push ./dev-bundle to a GitHub repo, then they run:
cairn install https://github.com/you/dev-bundle
```
`install` also accepts a local directory and skips anything already in your vault (never clobbers).

---

## Uninstall / undo

- Deactivate in a project: `cairn clear`.
- Remove the Claude wiring: delete `~/.claude/skills/cairn` and the `SessionStart` block from
  `~/.claude/settings.json`.
- Remove the tool + vault: `pipx uninstall cairn` (or delete the venv), then `rm -rf ~/.cairn`
  `~/.config/cairn`.
