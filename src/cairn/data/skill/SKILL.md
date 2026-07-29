---
name: cairn
description: Use Cairn to manage per-project skill/memory/model bundles, delegate cheap bulk work to a local model to save tokens, save/restore warm-start notes across sessions and machines, and pass messages between machines. Invoke when the user mentions cairn, profiles, switching setups, saving/loading session context, or offloading bulk work locally.
---

# Cairn

Cairn is a CLI on your PATH that manages this user's Claude Code setup as toggleable, cross-machine
bundles. Reach for these commands when relevant — they are cheap and safe.

## Save tokens: delegate bulk/mechanical work to a local model

When you have a **bulk or mechanical** subtask over already-loaded data — summarize a long blob,
classify many rows, extract fields, draft boilerplate — prefer delegating it instead of spending
API tokens:

```bash
cairn ask <task> "<prompt>"     # e.g. cairn ask summarize "<text>"
```

It runs on a local model (free tokens) and prints the result to stdout. If it exits non-zero with
"run this task inline instead", the local endpoint is unreachable — just do the task yourself.
Use it for cost savings on bulk work, **not** for latency-sensitive single questions.

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
