# Cairn — Backlog & Product Goals

> Living roadmap. Design detail lives in [SPEC.md](SPEC.md); engineering standards that **every**
> task must meet live in [CLAUDE.md](CLAUDE.md). This file is the running list of *what we're
> building and why* — keep it updated as tasks move.

## Status key
- `[ ]` pending · `[~]` in progress · `[x]` done · `[!]` blocked (note why)

---

## Product goals (what the user wants out of Cairn — the durable list)

Captured from every conversation so far. These are the *why*; the phased tasks below are the *how*.

1. **Centralized vault** — one home for all memories/skills, usable across every project.
2. **Grouping into profiles** — save named bundles ("dev-heavy" = a few skills + a couple memories +
   a model) and carry them as a group.
3. **Toggle on/off per project** — turn skills/memories on only for the projects that want them.
4. **Token optimization** — cut real cost, honestly (not naive "token maxing"):
   - **Local-model delegation** — offload cheap/bulk subtasks to local Ollama (free tokens), Claude stays driver.
   - **Warm-start** — distill each session into a small note so the next session skips expensive re-exploration.
5. **Local model support** — talk to local models (Ollama on the Mac Mini) from inside a Claude session;
   route work to them by task/complexity via explicit rules + per-profile model.
6. **Cross-machine** — the vault (memories/skills/profiles + Claude's own auto-memory) follows you between
   machines; sessions on different machines can hand knowledge/messages to each other.
7. **Simple & low-friction** — one easy-to-edit config file (TOML), minimal dependencies, **no admin**,
   CLI-first, installable without hassle, and drivable by Claude itself (ships its own skill).

---

## Cross-cutting engineering requirements (apply to EVERY task — enforced by CLAUDE.md)

These are not a phase; they are the definition of done for all work.

- [ ] **Heavy documentation** — both the *code* (docstrings, module/class intent) and *how to interact
  with it* (README, per-command usage, `--help` text). It's a public repo; treat docs as a deliverable.
- [ ] **High-quality, senior-level architecture** — OOP + SOLID, small focused classes, composition over
      inheritance, clear seams. No god-objects, no copy-paste.
- [ ] **Unit tests, AAA (Arrange-Act-Assert)** for every module, asserting real value:
  - assert **DATA in / DATA out** with exact expected values (not truthiness);
  - for every external call (filesystem / model / subprocess / network) assert it **happened**, **how
    many times** (`call_count`), and **with what exact payload**;
  - cover happy path **and** failure/edge cases; no weak/tautological tests that still pass when the
    logic breaks.
- [ ] **Security** — no shell-injection via unsanitized args, no arbitrary path traversal on
      symlink/vault operations, careful handling of external-import/trust boundaries, no secrets in
      config or logs. Review every task for vulnerabilities.

---

## Phase 0 — Scaffolding
- [x] **#0.1** Repo scaffold: `pyproject.toml` (hatchling, pipx-installable, `cairn` entry point),
      `src/` layout, pytest + ruff config, GitHub Actions CI (3.11–3.13), README dev section.
      CLI dispatch seam (`Command` protocol + injectable registry) so subcommands plug in without
      editing `main`. 4 AAA tests (version output, help, dispatch payload+count, unknown-command).
      Green: ruff clean, pytest 4/4.
- [ ] **#0.2** Config layer: load/validate `cairn.toml` + `profiles.toml` (TOML), typed models, clear
      errors on malformed config. (Tests: valid/invalid/missing, exact parsed values.)
- [ ] **#0.3** Vault model + paths: locate `~/.cairn/`, the pluggable sync interface seam
      (`pull/push/status`), machine identity. (Tests: path resolution, identity default = hostname.)

## Phase 1 — MVP (Vault + Profiles + Sync)  ← the whole toggleable-bundle vision
- [x] **#1.1** `cairn import` — copies skills (dirs) + memories (`*.md`) from `~/.claude` (or given
      dirs) into the vault; non-destructive, skips existing. `importer.py`, 3 tests.
- [x] **#1.2** `cairn use` / `cairn clear` — activation per SPEC Appendix A: pure `resolve_bundle`
      (merge, dedup, last-model-wins) + `activate`/`deactivate`. Manifest-tracked symlinks (skills →
      `.claude/skills/`, memories → `.claude/rules/`), model merge into `settings.local.json` with
      backup, `<project>/.cairn/` state, `.gitignore`, full rollback that removes only Cairn's links
      and restores the prior model. Validates before touching disk; refuses to clobber. `activation.py`,
      15 tests. (Deferred to #2.2: brief surfacing.)
- [x] **#1.3** `cairn status` / `cairn ls` — active profile(s) + machine/vault/sync summary; vault
      inventory. `commands.py`, covered by CLI integration tests. (Broken-link detection: deferred to
      `cairn doctor`, icebox #5.8.)
- [x] **#1.4** Sync backends: `off`/`folder`/`syncthing` (no-op — external tool owns sync) + `git`
      (injected runner, best-effort, swallows network failure). `sync.py`, 8 tests.

## Phase 2 — v1 (the cost-saving story)
- [x] **#2.1** `cairn ask` — local-model delegation. `delegate.py`: `Delegator` (task→model map,
      trailing-slash-safe endpoint, injected POST) + `DelegateUnreachable` fail-loud ("run this task
      inline instead", exit 1). Global `[delegate].enabled` gate. 6 tests. (Deferred: per-profile
      delegate flag as an advisory layer surfaced to Claude via the skill.)
- [x] **#2.4** Delegation workers — config-driven `[[worker]]` registry, two backends behind one
      abstraction (`workers.py`): **claude** (renders/installs `~/.claude/agents/cairn-<name>.md` with
      `model:` pinned to a tier; driver delegates via the Task tool) and **local** (Ollama over HTTP,
      `cairn workers run`). `cairn workers ls|sync|run`; `init` seeds `delegate` (Sonnet) +
      `delegate-fast` (Haiku) and syncs; skill teaches the driver to delegate. Explicit/driver-
      controlled by design — NOT the rejected auto-router. Docs: [DELEGATION.md](DELEGATION.md).
      18 tests (config parse, render/install idempotency, local-run payload, CLI ls/sync/run).
- [x] **#2.2** `cairn checkpoint` / `cairn brief` — warm-start. `checkpoints.py`: newest-first,
      machine-stamped blocks in `session-notes/<project>.md`; `latest_brief` returns the newest block.
      Checkpoint reads `--message` or stdin (Claude authors it). 4 tests. (Deferred: optional local
      distill pass for long briefs.)
- [x] **#2.3** `cairn sync-memory [--off]` — points `autoMemoryDirectory` at `<vault>/auto-memory/<proj>`
      so Claude's own auto-memory syncs across machines (SPEC Appendix D differentiator). `automemory.py`,
      3 tests.

## Phase 3 — v2 (cross-machine messaging)
- [x] **#3.1** Tier-0 mailbox — `cairn send` / `cairn inbox [--read]` over the synced vault (no daemon,
      no ports). `mailbox.py`: timestamp+sender filenames (collision-free), newest-first, non-destructive
      `read/` move; send/inbox call best-effort sync push/pull. 4 tests.
- [!] **#3.2** Tier-1 live LAN bridge — **deferred by design.** It's the only port-binding feature and
      SPEC marks it "build last, only if Tier-0 isn't enough." Tier-0 covers the stated need (carry
      knowledge between machines) with zero ports/admin, so this stays parked until a concrete real-time
      need appears.
- [x] **#3.3** Same-machine sessions — several Claude sessions on ONE machine share the vault but take
      distinct mailbox identities via `$CAIRN_MACHINE` (resolves over `[machine].name`, mirroring how
      `$CAIRN_HOME` overrides the vault root). `sessions.py`: host-scoped presence roster (register/
      heartbeat/ls/end/prune, traversal-safe names, corrupt-file-tolerant); `cairn session <action>` +
      `cairn broadcast` (one-to-many to live peers). Design in [SESSIONS.md](SESSIONS.md). 30 tests
      (24 module + 6 CLI). Verified end-to-end.
  - [ ] **#3.3a** Surface unread mail at SessionStart (additive, best-effort — must never break a session).
  - [x] **#3.3b** `cairn inbox --wait [--timeout N]` blocking receive, for turn-taking between sessions.
        `mailbox.wait_for_inbox` (injectable clock/sleep/poll, syncs each cycle, returns on first
        message or empty on timeout); dependency-free 1s poll. 6 tests (4 unit + 2 CLI, non-blocking).
  - [ ] **#3.3c** Optional auto-heartbeat on any command (accurate presence without explicit `session start`).

## Phase 4 — Distribution & polish
- [x] **#4.0** `cairn init` — one-time setup: scaffold vault + starter config (with a `default` profile
      and `[defaults].profile`), import existing `~/.claude` skills/memories, install the bundled skill,
      and merge a `SessionStart` hook into `~/.claude/settings.json` (non-destructive). Plus
      `cairn session-start` (hook target) that **auto-activates the default profile** and injects the
      latest warm-start brief with `reloadSkills` so it takes effect *this* session. `scaffold.py`,
      `claude_setup.py`, `session_start.py`; 14 tests. Verified end-to-end against temp dirs.
- [x] **#4.1** Bundled Cairn skill (`src/cairn/data/skill/SKILL.md`) — teaches Claude when to reach for
      `ask`/`checkpoint`/`use`/`send`. Installed by `cairn init`.
- [x] **#4.2** Docs pass: README now has setup/quickstart, command reference, config reference, and
      recipes (network-drive vault, git vault, second machine). SPEC has the positioning section.
- [x] **#4.3** Packaging proven: `python -m build` produces a wheel that **includes the bundled skill
      data** (`cairn/data/skill/SKILL.md`); fresh-venv install runs `cairn --version` and `cairn init`
      correctly (skill installed from the packaged data). pipx uses the same mechanism. Single-binary
      path still scoped for later.
- [x] **#4.4** Positioning & non-goals section added to SPEC (wedge = profile bundles + cross-machine;
      non-goals = not a proxy/router, not a note UI, not a generic dotfile manager).

## Phase 5 — Icebox (speculative — captured, not committed)

Ideas from the "what else could this be" brainstorm. Each must earn its place by strengthening the
two moat pillars (**bundle-toggle** or **cross-machine**) or the honest token-savings story. Not
scheduled; promote into a phase when it proves worth the weight.

*Extends the bundle wedge:*
- [x] **#5.1** Bundle **MCP servers** into profiles: a profile's `[profiles.X.mcp.<server>]` tables are
      merged into the project's `.mcp.json` on activate (never clobbering a hand-added server, tracked
      in the manifest) and removed on clear. Merges across inheritance + multiple profiles. 6 tests.
      (Hooks-in-profiles deferred: risks colliding with the init-installed SessionStart hook — revisit
      if a concrete need appears.)
- [x] **#5.2** Profile **inheritance** — `extends` (parents first, child overrides), cycle-detected.
- [ ] **#5.3** **Auto-activation** by project markers (pyproject → python, git remote → work). (Partly
      served already by `[defaults].profile` auto-activation via the SessionStart hook.)

*Extends cross-machine:*
- [x] **#5.4** `cairn handoff <machine>` / `cairn resume` — packages the project's active profile(s) +
      latest brief + a note into a marked mailbox message; `resume` surfaces the newest handoff.
      `handoff.py`, 5 + 2 tests.
- [x] **#5.5** `cairn recall "<query>"` — full-text search across memories + warm-start notes via stdlib
      SQLite FTS5 (BM25, highlighted snippets); files stay truth, index built in-memory per query.

*Proves the savings / trust & ops:*
- [ ] **#5.6** Cost/savings analytics — spend per profile + how much delegation & warm-start actually saved.
- [x] **#5.7** `cairn use --dry-run` — validates the bundle and prints the plan without touching anything.
- [x] **#5.8** `cairn doctor` — vault/config/profiles/default-profile/dangling-links/sync/delegate checks.

*Model/agent-agnostic (keep in mind; don't build yet):*
- [ ] **#5.11** `AgentAdapter` seam — activation currently targets Claude Code paths (`.claude/skills`,
      `.claude/rules`, `settings.local.json`). Factor the *target* behind an adapter so other agents
      (Cursor, Codex, Gemini CLI, …) can be activation targets. Everything else is already
      agent-neutral: vault, profiles, sync, mailbox, warm-start, and `cairn ask` (any local model).
      Focus stays Claude for now; this is the future-proofing note.

*Vault backends — shared drive / git repo (single-user, multi-machine-optional):*
- [x] **#5.12** Vault on a shared network drive or git repo. `cairn init --vault-path <dir>` puts the
      vault on a mounted share (with `--sync folder`) or a git checkout (`--sync git`) and remembers the
      location in `~/.config/cairn/location` (no env var needed). Recipes documented in the README.

*Growth (later, flag caution):*
- [x] **#5.9** Shareable profiles — `cairn export <profile> <dir>` packages a flattened profile + its
      skills/memories/mcp into a bundle (JSON manifest + assets); `cairn install <git-url|dir>` clones
      (injectable cloner) and merges it into the vault, skipping existing names. `bundle.py`, 5 + 2 tests.
- [ ] **#5.10** Shared/team read-only vault overlay — real, but drifts toward platform territory; park it.

**Explicitly resisting (scope discipline):** no full auto-router · no note-editing UI (Obsidian's lane) ·
not a generic dotfile manager (`stow` exists). Every add passes: *does this make the bundle or the
cross-machine story better?*
