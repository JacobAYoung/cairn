---
name: cairn
description: Use Cairn to manage per-project skill/memory/model bundles, delegate cheap bulk work to a local model to save tokens, save/restore warm-start notes across sessions and machines, and pass messages between machines. Invoke when the user mentions cairn, profiles, switching setups, saving/loading session context, or offloading bulk work locally.
---

# Cairn

Cairn is a CLI on your PATH that manages this user's Claude Code setup as toggleable, cross-machine
bundles. Reach for these commands when relevant — they are cheap and safe.

## Save budget: delegate heavy sub-tasks to cheaper worker models

You (the driver) run on an expensive model. Cairn configures **workers** — cheaper models to hand
well-scoped sub-tasks to — so your budget is spent on the reasoning and decisions only you should
make. See what's available with `cairn workers ls`. Two kinds:

**1. Claude worker subagents (default: `cairn-delegate` on Sonnet, `cairn-delegate-fast` on Haiku).**
Spawn them with the **Task tool** instead of doing the work yourself:

- **`cairn-delegate`** (Sonnet) — substantial, well-scoped sub-tasks: searching/reading across many
  files and reporting findings, summarizing or extracting from large text, drafting boilerplate,
  mechanical multi-file edits, running and collating test/build output.
- **`cairn-delegate-fast`** (Haiku) — rote, high-volume work with an unambiguous answer: formatting,
  field extraction, bulk edits, collating grep/log output, simple classification.

Rule of thumb: **if a sub-task is well-defined and its bulky inputs don't need to stay in your
context, delegate it and keep only the result.** Give the worker a self-contained task and the exact
output shape you want back. (If `cairn workers ls` shows nothing, run `cairn workers sync`.)

**2. Local models (free, off-API)** for bulk/mechanical generation when Ollama is set up:

```bash
cairn workers run <name> "<prompt>"   # a configured local worker, e.g. summarizer
cairn ask <task> "<prompt>"           # or the [delegate] task→model mapping
```

If a local call exits non-zero with "run this task inline instead", the endpoint is unreachable —
just do the task yourself. Use local delegation for cost on bulk work, not latency-sensitive asks.

## Warm-start: end and resume sessions with continuity

At the **end** of a substantive work session, save a short brief so the next session (on any
machine) starts warm:

```bash
cairn checkpoint -m "Decisions made, open threads, where things live."
```

The latest brief is auto-loaded at session start via the hook; you can also read it with
`cairn brief`.

## Profiles (setup bundles)

```bash
cairn ls                 # what's in the vault (skills · memories · profiles)
cairn use <profile>      # activate a bundle in this project (persists)
cairn status             # what's active here + machine/vault/sync
cairn clear              # deactivate
```

## Cross-machine

```bash
cairn send <machine> "<message>"   # leave a note for another machine
cairn inbox                        # read notes left for this machine
```

Only surface these when they help the user's actual task. Do not run `cairn use`/`clear` without a
reason to change the active setup.
