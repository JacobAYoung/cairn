# Cairn — working spec (v0)

> **One line:** a small CLI + one editable config file that turns Claude Code's scattered
> primitives (skills, per-scope settings, per-subagent model choice, `~/.claude`) into a
> **portable, toggleable, cross-machine vault** — with cheap local-model delegation and
> warm-start memory to cut cost.

*Working name: **Cairn** (a stack of stones that marks a path — you stack skills/memories and
it marks the way across projects and machines). Alternatives on the table: Loom, Ferry, Warren.
Rename freely.*

---

## Design principles (your stated goals, made into rules)

1. **No admin, ever, for core features.** If a feature needs elevated privileges, it's optional and off by default.
2. **Minimal dependencies.** Prefer stdlib + one or two tiny libs. No heavy runtime, no service to babysit.
3. **One config file a human can actually edit.** Comments allowed. Not "huge crazy customization" — a handful of clear knobs.
4. **CLI-first, no UI.** Installable the way people already grab command-line tools.
5. **Claude can drive it.** It ships its own skill so a Claude session *knows the commands exist* and reaches for them.
6. **Reversible & non-destructive.** Toggling a profile never copies/duplicates or clobbers; it symlinks and can be undone instantly.

---

## The five pillars

| Pillar | What it does | Difficulty | Phase |
|---|---|---|---|
| **Vault** | One canonical home for all skills + memories; syncable across machines | Easy | MVP |
| **Profiles** | Named bundles of `{skills, memories, model}` you activate per project | Easy–Med | MVP |
| **Delegate** | Hand cheap subtasks to local Ollama models (free tokens); Claude stays the driver | Medium | v1 |
| **Warm-start** | Distill each session into a tiny note; load it next time to skip re-exploration | Medium | v1 |
| **Bridge** | Session ↔ session messaging across machines (Tier 0: via synced vault; Tier 1: live LAN) | Med–Hard | v2 |

---

## Layout

```
~/.cairn/                     # the vault — this whole folder is what syncs across machines
  skills/                     # canonical home for every skill you own
  memories/                   # canonical home for every memory
  session-notes/              # warm-start checkpoints, one file per project
  mailbox/                    # Tier-0 cross-machine messages (per-machine files)
  profiles.toml               # named bundles  (human-edited)
  cairn.toml                  # global config: routing, sync, bridge  (human-edited)
```

A project that has a profile active gets a `.cairn` marker file recording which profile is on,
so `cairn status` works and it survives across sessions.

---

## Config format decision

**TOML**, not JSON. Reason: your #3 goal is "easy to mess with," and JSON has no comments and
punctuation noise. TOML reads like an ini file, allows `# comments`, and Python 3.11+ parses it
with zero external deps (`tomllib`). *(Flip to YAML if you'd rather; flip to JSON only if you want
it to match Claude Code's own `settings.json` exactly.)*

### `profiles.toml`
```toml
[profiles.dev-heavy]
skills   = ["develop", "audit-and-review", "code-review"]
memories = ["code-conventions", "git-hygiene"]
model    = "opus"          # what Claude Code runs as when this profile is active

[profiles.research]
skills   = ["web-notes"]
memories = []
model    = "sonnet"
delegate = true            # allow offloading cheap subtasks to local models
```
Profiles compose: `cairn use dev-heavy,research` merges both.

### `cairn.toml`
```toml
[sync]
mode = "syncthing"         # "syncthing" | "folder" | "git" | "off"
# folder mode just points at an already-synced dir (iCloud/Dropbox):
# path = "~/Library/Mobile Documents/.../cairn"

[delegate]
enabled  = true
endpoint = "http://mac-mini.local:11434"   # Ollama on the Mac Mini, over the LAN
default  = "qwen2.5:14b"
tasks    = { summarize = "qwen2.5:14b", classify = "nemotron-mini", draft = "llama3.1:8b" }

[bridge]
enabled = false            # Tier-1 live LAN chat — off by default (the only firewall-touching part)
port    = 8787
```

---

## Pillar 1 — Vault + sync

- `~/.cairn/` is the single source of truth. `cairn import` pulls your existing `~/.claude/skills`
  and project memories into it once.
- **Activation copies nothing** — `cairn use <profile>` symlinks the profile's skills/memories into
  the project's `.claude/skills/` and drops the profile's `model` into `.claude/settings.local.json`.
  Edits flow back to the vault (it's the real file), so they sync automatically.
- `cairn clear` removes the symlinks. Instant, reversible, no duplication.
- **Sync is pluggable, and git is *not* the recommended default.** You asked "is a git repo the worst
  thing?" — it's not the worst, but the commit/push/pull dance and merge conflicts on notes are
  friction. Better fits:
  - **Syncthing** — peer-to-peer, no server, no admin, auto-syncs the folder between your machines. Best fit.
  - **A cloud-synced folder** (iCloud/Dropbox) — dead simple, zero setup, `mode = "folder"`.
  - **Git** — kept as an option for people who want version history; `cairn sync` wraps commit/pull so you never type git.
  - *(macOS symlink note: symlinks need no admin on Mac/Linux. Windows would need copy-with-writeback — Mac-first for now.)*

---

## Pillar 2 — Profiles (the killer feature, and the easiest)

This is the piece that doesn't exist anywhere today and delivers the most: grouping + per-project
toggle + per-project model, all from one file. Commands:

```
cairn use dev-heavy          # activate a bundle in the current project
cairn use dev-heavy,research # merge two
cairn clear                  # deactivate
cairn status                 # what's active here + globally
cairn ls                     # list profiles / skills / memories in the vault
```

---

## Pillar 3 — Delegate (the real token saver)

Claude stays your terminal. When a subtask is cheap and mechanical, Claude calls out to a **local**
model on the Mac Mini instead of spending API tokens. Two implementations, pick one:

- **Simple (recommended first):** a CLI `cairn ask <task> "<prompt>"` that hits the Ollama endpoint
  and prints the answer. Claude invokes it via Bash. Zero new protocol, works today.
- **Fancier:** expose it as an MCP server so it shows up as a native tool. More polish, more setup.

Honest scope: this saves **real dollars** because it moves cheap work off the metered model onto
hardware you already run — that's the (b) lever ("stop using an expensive model for trivial work").
A pure "auto-classify every prompt to a cheaper Claude tier" router is deliberately **not** the
default, because the classifier call eats most of the savings. Explicit rules + local offload win.

---

## Pillar 4 — Warm-start (distill, don't accumulate)

The correct framing of your token-saving idea:

- **End of session:** `cairn checkpoint` sends the session's key outcomes to a *local* model, which
  writes a compact `session-notes/<project>.md` — decisions made, what was learned, where things live.
- **Start of next session:** the latest checkpoint (small) is injected, so Claude skips the expensive
  *rediscovery* — the tool calls, the re-reading, the re-reasoning.
- **Why this saves money:** you spend a little cheap input to avoid a lot of expensive output +
  tool-call round-trips. The distillation itself runs free on the Mac Mini. Accumulating raw context
  would do the opposite, so the tool distills instead of hoards.

---

## Pillar 5 — Bridge (cross-machine sessions)

Your real need: "I was doing stuff on one session, I want that knowledge on my laptop." That's
**memory transport**, and the synced vault already solves it. Messaging is a thin layer on top.

- **Tier 0 — mailbox over the synced vault (default, no daemon, no ports):**
  ```
  cairn send laptop "here's the context from the API refactor: ..."
  cairn inbox                 # read messages waiting for this machine
  ```
  Writes/reads files under `~/.cairn/mailbox/`. Async, zero admin. Because it's the same synced vault,
  memory carries across for free — this *is* your Obsidian-style cross-computer vault.
- **Tier 1 — live LAN bridge (opt-in, `[bridge] enabled = true`):** a tiny local listener for
  real-time session-to-session chat. This is the only feature that can trigger a firewall dialog
  (still no admin on Mac to bind a high port). Off by default; build last, only if Tier 0 isn't enough.

---

## CLI surface (whole thing)

```
cairn import                    # one-time: pull existing ~/.claude skills+memories into the vault
cairn ls [skills|memories|profiles]
cairn use <profile[,profile]>   # activate in current project
cairn clear                     # deactivate
cairn status                    # active profile(s) here + global config summary
cairn sync                      # push/pull the vault (wraps syncthing/git/folder)
cairn ask <task> "<prompt>"     # delegate a subtask to a local model
cairn checkpoint                # distill this session into a warm-start note
cairn brief                     # print the latest warm-start note for this project
cairn send <machine> "<msg>"    # Tier-0 cross-machine message
cairn inbox                     # read incoming messages
```

---

## Install & distribution

- **Build as:** a Python CLI (you already have Python everywhere), installable via **pipx**
  (`pipx install cairn`) — isolated, no admin, on PATH. Designed so it *could* later ship as a
  single Go/Rust binary + a Homebrew tap for people who don't want Python.
- **"Claude can find and use it":** it's a plain command on PATH **and** it ships a bundled skill
  (`cairn/SKILL.md`) that documents its commands, so a Claude session knows to reach for `cairn use`,
  `cairn ask`, etc. without you explaining it each time.
- **Dependencies target:** stdlib + `tomllib` (built in on 3.11+) + `httpx` (for local-model calls).
  That's it for the MVP. No database, no service, no admin.

---

## Appendix A — Activation mechanics (the part that must not break a live session)

The whole "toggle" promise lives or dies here. Details:

### What `cairn use <profile>` actually does
1. **Read** the profile from `profiles.toml` → resolve the list of skill + memory names.
2. **Validate** every named skill/memory exists in the vault. Missing → hard error, change *nothing*
   (no half-applied state).
3. **Snapshot** the project's current `.claude/` state into `.cairn/backup/` (see rollback below).
4. **Link skills:** for each skill, create a symlink `.claude/skills/<name>` → `~/.cairn/skills/<name>`.
   Cairn only ever touches links it owns — it writes a manifest (`.cairn/manifest.json`) listing
   exactly which paths it created, so `clear` removes *only* those and never a hand-placed file.
5. **Link memories:** same, into wherever the project reads memory from.
6. **Write model:** merge `model = "<profile model>"` into `.claude/settings.local.json` (merge, not
   overwrite — preserve any keys already there; record the prior value in the manifest).
7. **Write the marker:** `.cairn` file records active profile(s) + timestamp.

### Does this break a session that's already running?
This is the real risk, so it's a designed constraint, not an afterthought:
- **Skills/memories:** Claude Code discovers these at session start, so linking new ones mid-session
  won't hot-load — but it also **can't corrupt the running session**, because we only *add* symlinks;
  we never delete or rewrite a file the live session already has open. New profile takes effect on the
  next session. `cairn use` prints `"active next session — restart Claude to load"` so it's honest.
- **Model change:** writing `settings.local.json` mid-session is likewise picked up next launch, not
  retroactively. Same honest message.
- **Net rule:** `use`/`clear` are **safe to run anytime** (never corrupt a live session) but **apply on
  next session**. That's a deliberate, clearly-communicated boundary — simpler and safer than trying to
  hot-swap a running process.

### Rollback / safety
- `.cairn/manifest.json` is the source of truth for "what did Cairn touch." `cairn clear` reverses
  exactly that manifest: remove Cairn-created links, restore the recorded prior `model` value.
- `cairn clear` on a project with hand-edited `.claude/skills/` leaves the hand-edited ones alone —
  it only removes links whose target is inside `~/.cairn/`.
- If the vault folder is unavailable (sync not mounted), symlinks dangle harmlessly; `cairn status`
  detects and reports broken links rather than silently failing.

### Why symlinks, not copies
Copies would double every file and, worse, *fork* them — you'd edit a skill in a project and the
vault copy would drift. Symlinks keep one canonical file, so an edit in any project writes back to the
vault and syncs everywhere. (Windows is the exception — it needs copy-with-writeback or dev-mode
symlinks; Mac/Linux first.)

---

## Appendix B — Delegate & warm-start internals

### `cairn ask <task> "<prompt>"`
- Looks up `task` in `[delegate].tasks` → model name; falls back to `[delegate].default`.
- POSTs to the Ollama `endpoint` (`/api/generate`, `stream:false`), prints the completion to stdout.
- **Reachability guard:** endpoint is on another machine (`mac-mini.local`). If it's unreachable
  (laptop off-network, Mini asleep), Cairn must **fail loud and useful** — exit non-zero with
  `"delegate endpoint unreachable; run this task inline instead"` — so Claude falls back to doing it
  itself rather than hanging. Timeout is short (a few seconds to connect).
- **What Claude sees:** because it's a plain CLI, Claude calls it via Bash and reads stdout. The
  shipped skill tells Claude *when* to reach for it: "for bulk summarize/classify/extract/draft over
  already-loaded data, prefer `cairn ask` — it's free tokens on local hardware."
- **Honest limit:** round-trips to a 14B local model are *slower* than Claude answering inline. So the
  guidance is "delegate cheap **bulk/mechanical** work, not latency-sensitive single questions." The
  win is cost, not speed.

### `cairn checkpoint`
The warm-start distiller. Design decisions:
- **Input:** Claude, at end of a work session, calls `cairn checkpoint` and pipes it a short structured
  brief (decisions, open threads, file locations) — *Claude* produces the brief because it has the
  session context; Cairn just persists + indexes it. (Simpler and more accurate than Cairn trying to
  scrape a transcript it can't see.)
- **Optional distill pass:** if the brief is long, Cairn runs it through the local `summarize` model to
  compress — free, on the Mini.
- **Storage:** `~/.cairn/session-notes/<project>.md`, append-only with a dated heading, newest on top.
  Syncs with the vault, so a checkpoint written on the desktop is *already on the laptop*.
- **Load:** `cairn use` (and a `cairn brief` command) prints the latest checkpoint so Claude can pull it
  in at session start. Small input cost, skips the expensive rediscovery.
- **Why this is the right token lever:** we spend cheap **input** to avoid expensive **output +
  tool-call round-trips** (re-reading files, re-deriving decisions). Accumulating raw history would
  bloat every turn and cost *more* — so checkpoints are distilled, capped, and newest-first.

---

## Phasing

- **MVP (a weekend):** Vault + import + Profiles + folder/Syncthing sync. This alone is the whole
  Obsidian-style toggleable-bundle vision and ships value immediately.
- **v1:** Delegate (local Ollama offload) + Warm-start checkpoints. The cost-saving story.
- **v2:** Tier-0 mailbox, then optional Tier-1 live bridge.

---

## Open decisions (yours to make — I picked defaults above)

1. **Config format:** TOML (my pick) vs YAML vs JSON.
2. **Sync mechanism default:** Syncthing (my pick) vs a cloud folder vs git-wrapped.
3. **Name:** Cairn (my pick) / Loom / Ferry / something you like better.
4. **Language/packaging:** Python+pipx now (my pick) vs go-straight-for-a-binary.
```