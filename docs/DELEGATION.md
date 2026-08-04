# Cairn — Delegation Workers

*Spec + reference for saving the expensive model's budget by handing sub-tasks to cheaper models.*

The driver (your primary Claude session) runs on a costly model. A **worker** is a cheaper model you
let the driver delegate well-scoped sub-tasks to, so the expensive model's budget is spent only on
the reasoning and decisions that actually need it. Workers are **pure config** — one registry, two
backends — so adding one never touches code.

This is the *explicit, driver-controlled* form of delegation. It is deliberately **not** an
auto-classifying prompt router (see [SPEC.md](SPEC.md) positioning & non-goals): the driver always
decides what to hand off. That's what keeps the savings real instead of a router that eats them.

---

## The registry

Declare workers as `[[worker]]` array-of-tables in `cairn.toml`:

```toml
[[worker]]
name    = "delegate"          # → subagent "cairn-delegate"
backend = "claude"
model   = "sonnet"            # Claude tier
role    = "Well-scoped sub-tasks: search many files, summarize/extract, draft, multi-file edits."

[[worker]]
name    = "delegate-fast"
backend = "claude"
model   = "haiku"
role    = "Rote bulk work: formatting, extraction, bulk edits, collation, simple classification."

[[worker]]
name     = "summarizer"
backend  = "local"
model    = "qwen2.5:14b"
endpoint = "http://localhost:11434"
role     = "Summarize/extract from large text, off-API and free."
```

| Field | Meaning |
|---|---|
| `name` | Worker id (safe chars). A `claude` worker becomes subagent `cairn-<name>`. |
| `backend` | `claude` (a Claude Code subagent) or `local` (an Ollama-style HTTP model). |
| `model` | For `claude`: an alias **or a pinned full model ID** (see below). For `local`: the Ollama model name. |
| `role` | One line describing what to send it — used in the generated subagent and in `workers ls`. |
| `endpoint` | `local` only; defaults to `http://localhost:11434`. |

### Pinning a model version (alias vs full ID)

Cairn passes `model` through **verbatim** into the subagent's `model:` frontmatter, and Claude Code
accepts either form there:

- **Alias — floating, tracks the latest:** `sonnet`, `opus`, `haiku`, `fable`, or `inherit`.
  `model = "sonnet"` always resolves to whatever the current Sonnet is.
- **Full ID — pinned to a specific version:** e.g. `model = "claude-sonnet-4-6"`,
  `model = "claude-haiku-4-5-20251001"`, `model = "claude-opus-5"`. Use this when you want a worker
  locked to an exact version regardless of future releases.

Cairn does not maintain an allowlist (that would go stale the day a new model ships) — any string you
write is honored, so new model IDs work immediately. `cairn workers ls` prints the exact `model`
value so you can see at a glance whether a worker is floating or pinned.

---

## The two backends

### `claude` — a cheaper subagent the driver delegates to

`cairn workers sync` (also run by `cairn init`) **generates** `~/.claude/agents/cairn-<name>.md` from
the worker's `role` + a shared operating-rules template, with `model:` pinned to the tier. The driver
then delegates to it with the **Task tool**, and Claude Code runs that sub-task on the cheaper model.

Generation is idempotent and non-destructive — only `cairn-*.md` files are (re)written; hand-authored
agents are left alone. Editing a worker = edit config + `cairn workers sync`.

### `local` — a free, off-API model over HTTP

`local` workers run on Ollama (or any compatible `/api/generate` endpoint):

```bash
cairn workers run summarizer "<prompt>"
```

If the endpoint is unreachable it fails loud ("run this task inline instead") so the driver falls
back rather than hanging. This is the "go a step further to save more" tier — free per call, but
requires Ollama installed and the model pulled.

---

## Commands

| Command | Purpose |
|---|---|
| `cairn workers ls` | List configured workers (backend, model, delegation target, role) |
| `cairn workers sync [--claude-dir DIR]` | (Re)generate the `claude` workers as subagents |
| `cairn workers run <name> "<prompt>"` | Run a `local` worker over HTTP |
| `cairn init` | Seeds the two default `claude` workers and runs `sync` |

The bundled Cairn **skill** teaches the driver to reach for these: if a sub-task is well-defined and
its bulky inputs don't need to stay in the driver's context, delegate it and keep only the result.

---

## Defaults & how the savings actually land

`cairn init` seeds two `claude` workers out of the box: **`delegate`** (Sonnet) for substantial
sub-tasks and **`delegate-fast`** (Haiku) for rote bulk work. On a Claude subscription this shifts
that work off the expensive tier and onto Sonnet/Haiku *within the same auth* — no separate bill.

The biggest wins come when the delegated model reads the **raw inputs itself** (many files, long
logs) so that bulk never enters the driver's context — you pay for the compact result, not the
material. Give the worker a self-contained task and the exact output shape you want back.
