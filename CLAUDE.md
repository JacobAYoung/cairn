# Cairn — Project Context & Engineering Standards

## What this is

Cairn is a small **CLI + one TOML config file** that turns Claude Code's scattered primitives
(skills, per-scope settings, per-subagent model choice, `~/.claude`) into a **portable, toggleable,
cross-machine vault** — with cheap local-model delegation and warm-start memory to cut token cost.

- **Design:** [SPEC.md](SPEC.md) — pillars, config, activation/sync/delegate mechanics, verified
  Claude Code integration points (Appendix D).
- **Roadmap & product goals:** [BACKLOG.md](BACKLOG.md) — what we're building and why; keep it updated
  as tasks move.

Resolved decisions: **TOML** config · **Syncthing** default sync · name **Cairn** · **Python + pipx**
(designed so it could later ship as a single binary). No admin ever for core features.

---

## Code Quality Standards — the definition of done for EVERY change

These are non-negotiable and apply to all code, retroactively when touching existing files. This is a
public repo; treat quality and documentation as deliverables, not afterthoughts.

### Documentation (heavy, on purpose)
- **Code:** every module, public class, and public function has a docstring stating *intent and
  contract* (what it does, inputs/outputs, side effects, failure modes) — not a restatement of the code.
- **Usage:** every CLI command has clear `--help` text and an entry in the README/command reference.
  If a feature isn't documented for a user to *interact* with, it isn't done.
- **Comments:** only where the *why* is non-obvious (a constraint, workaround, invariant). Never a
  comment that just restates the code.

### Architecture (senior-level, SOLID/OOP)
- Small, focused classes — one responsibility each. Compose; don't inherit for reuse.
- Clear seams/interfaces (e.g. the sync backend is an interface with `pull/push/status`; adding a
  backend is a new class, no changes elsewhere). Depend on abstractions at boundaries.
- Name things so a reader needs no comment to understand them. No god-objects, no duplication.

### Testing — AAA, and it must have teeth
Every module gets a matching test file. Tests validate **actual behavior**, not "it runs."
- **Arrange-Act-Assert** structure, explicitly.
- Assert **DATA in / DATA out** with *exact* expected values — never mere truthiness.
- For **every external interaction** (filesystem, subprocess, model/HTTP call, injected dependency)
  assert: that it **happened (or didn't)**, **how many times** (`call_count == N` — catches
  double-writes / missing caching), and **with what exact payload** (path, args, request body, model).
- Cover the **happy path AND** failure/edge cases (bad input, missing file, unreachable endpoint,
  dangling symlink, conflict).
- A test that still passes after you break the logic isn't testing enough — delete weak/tautological
  tests. No duplicate tests that assert the same thing.
- Do **not** mock the filesystem in integration tests where a temp dir is feasible — operate on a real
  temp vault/project and assert resulting on-disk state (symlinks created, manifest contents, files moved).

### Security
- Never build shell commands from unsanitized input; prefer `subprocess` arg lists over shell strings.
- Validate and confine all path/symlink operations to expected roots — no traversal outside the vault
  or project; refuse to remove links Cairn didn't create (honor the manifest).
- Respect Claude Code trust boundaries (external-import approval, `autoMemoryDirectory` trust gate).
- No secrets written to config, logs, or the vault. Fail loud on unexpected errors — never swallow.

### Error handling
- Catch specific exceptions; surface clear, actionable messages (CLI: non-zero exit + a useful line).
- Validate inputs at the boundary (CLI args, config); trust internal code.
- Sync/network is best-effort and non-blocking — degrade with a warning, never hang or corrupt state.

---

## Workflow

1. Pick the next unchecked task in [BACKLOG.md](BACKLOG.md) phase order; mark it `[~]` before starting.
2. Meet every standard above — including tests and docs — *as part of the task*, not later.
3. Mark `[x]` with a one-line note when done; commit with a clear message.
4. Never break existing behavior; keep the test suite green.
