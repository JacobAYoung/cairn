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
- [ ] **#2.1** `cairn ask` — local-model delegation (Ollama endpoint, task→model map, reachability guard,
      fail-loud). Two switches (global + per-profile).
- [ ] **#2.2** `cairn checkpoint` / `cairn brief` — warm-start: persist Claude-authored brief, optional
      local distill, newest-first per-project store, load at session start.
- [ ] **#2.3** Point `autoMemoryDirectory` at the synced vault (opt-in) so Claude's own auto-memory syncs
      across machines — the strongest cross-machine differentiator (see SPEC Appendix D).

## Phase 3 — v2 (cross-machine messaging)
- [ ] **#3.1** Tier-0 mailbox — `cairn send` / `cairn inbox` over the synced vault (no daemon/ports).
- [ ] **#3.2** Tier-1 live LAN bridge — opt-in real-time session chat (`[bridge].enabled`), built last.

## Phase 4 — Distribution & polish
- [ ] **#4.1** Ship the bundled Cairn skill so Claude knows the commands exist and when to use them.
- [ ] **#4.2** Full docs pass: README, command reference, quickstart, config reference.
- [ ] **#4.3** Packaging: pipx install path proven; single-binary path scoped for later.
- [ ] **#4.4** Positioning section in SPEC (wedge = profiles + cross-machine; non-goals = don't compete as
      a generic vault/router) — from the viability discussion.

## Phase 5 — Icebox (speculative — captured, not committed)

Ideas from the "what else could this be" brainstorm. Each must earn its place by strengthening the
two moat pillars (**bundle-toggle** or **cross-machine**) or the honest token-savings story. Not
scheduled; promote into a phase when it proves worth the weight.

*Extends the bundle wedge:*
- [ ] **#5.1** Bundle **MCP servers + hooks** into profiles (toggle every Claude Code primitive, not
      just skills/memories) — the most on-brand expansion.
- [ ] **#5.2** Profile **inheritance** (a `base` profile others extend) — DRY config.
- [ ] **#5.3** **Auto-activation** — pick a profile from project markers (pyproject → python, git remote
      → work) so the toggle is invisible.

*Extends cross-machine:*
- [ ] **#5.4** `cairn handoff` / `cairn resume` — package active profile + latest checkpoint + a note on
      one machine, reconstruct on another. The headline cross-machine flow.
- [ ] **#5.5** `cairn recall "<query>"` — search accumulated warm-start notes (grep, or local-embedding
      search on the Mac Mini). Ties warm-start + local models.

*Proves the savings / trust & ops:*
- [ ] **#5.6** Cost/savings analytics — spend per profile + how much delegation & warm-start actually saved.
- [ ] **#5.7** `cairn use --dry-run` — preview exactly what would link/change before touching anything.
- [ ] **#5.8** `cairn doctor` — vault integrity, broken links, sync state, Ollama reachability.

*Growth (later, flag caution):*
- [ ] **#5.9** Shareable profiles — `cairn install <url>` a bundle a friend can use (the personal→friends path).
- [ ] **#5.10** Shared/team read-only vault overlay — real, but drifts toward platform territory; park it.

**Explicitly resisting (scope discipline):** no full auto-router · no note-editing UI (Obsidian's lane) ·
not a generic dotfile manager (`stow` exists). Every add passes: *does this make the bundle or the
cross-machine story better?*
