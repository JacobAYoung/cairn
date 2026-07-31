# Cairn — Same-Machine Sessions

*Spec + reference for talking between multiple Claude Code sessions running on **one** computer.*

This is the local counterpart to [Pillar 5 — cross-machine messaging](SPEC.md#pillar-5--bridge-cross-machine-sessions).
Same Tier-0 philosophy (**files in the vault, no daemon, no ports, no admin**); the only new idea is
giving each session on a single machine its own **mailbox identity** so they can address each other.

---

## Why

The mailbox (`send`/`inbox`/`handoff`/`resume`) addresses a *machine* — its identity is the hostname
(`[machine].name` in `cairn.toml`). That is exactly right for desktop↔laptop, but it means two Claude
sessions on the **same** machine share one identity: they'd read each other's mail *and their own*, with
no way to tell sender from recipient.

People increasingly run several Claude Code sessions side by side on one machine — one per worktree,
one planning while another implements, a "reviewer" watching a "builder." Those sessions want a cheap,
persistent back-channel to pass context, hand off a task, or ping "I'm done, your turn." This feature
makes that a first-class, zero-setup path.

---

## The model

**One vault, many identities.** All sessions on the machine share the single `~/.cairn` vault (and its
one `mailbox/`). Each session picks a distinct identity by exporting **`CAIRN_MACHINE`** in its shell:

```bash
# terminal 1
export CAIRN_MACHINE=builder
# terminal 2
export CAIRN_MACHINE=reviewer
```

From then on every mailbox command uses that identity as *both* its inbox address and its sender tag.
`send`/`inbox`/`broadcast`/`handoff`/`resume` need no other change — they already key off the resolved
machine name; `CAIRN_MACHINE` just overrides what that name is, per shell.

### Identity resolution (precedence)

The effective identity is resolved once per command, highest precedence first:

1. **`$CAIRN_MACHINE`** — per-session override (this feature). Empty/whitespace is treated as unset.
2. **`[machine].name`** in `cairn.toml` — the machine's configured mailbox name.
3. **short hostname** — the default when nothing is set.

This deliberately mirrors how **`$CAIRN_HOME`** overrides the *vault root*: same shape (env wins over
file wins over default), so the two knobs compose — `CAIRN_HOME` picks *which vault*, `CAIRN_MACHINE`
picks *who you are within it*. `cairn session whoami` prints the resolved identity and its source.

---

## The roster

Identity alone lets two sessions talk *if they already know each other's names*. The **roster** adds
discovery and fan-out: a directory of tiny presence files, one per session, under `~/.cairn/sessions/`.

```
~/.cairn/sessions/
  builder.json     {"name","host","project","created_utc","last_seen_utc"}
  reviewer.json
```

- **`cairn session start [name]`** — register (or heartbeat) a session. Idempotent: re-running refreshes
  `last_seen_utc` and `project` but preserves `created_utc`. With no argument it uses `$CAIRN_MACHINE`.
- **`cairn session ls`** — list this machine's sessions with presence: `●` live (checked in within the
  staleness window, 15 min) or `○` stale, plus the project each is working in and how long since it was
  last seen. Your own session is marked `<- you`.
- **`cairn session whoami`** — show this shell's resolved identity and where it came from.
- **`cairn session end [name]`** — drop a session from the roster.
- **`cairn session prune`** — drop every session not seen within the staleness window.

### Broadcast

- **`cairn broadcast "<msg>"`** — deliver a message to *every other* live session on this machine (a
  `send` to each roster peer except yourself). `--include-self` also copies it to your own inbox. This is
  the one-to-many complement to the one-to-one `send`.

---

## Storage & sync interaction

Presence is **machine-local runtime state**, not portable config, so each record carries the real `host`
it was created on. Listing/pruning/broadcast filter to the current host, so even when the vault *is*
synced across machines (Syncthing/folder/git), one machine never sees or prunes another's sessions. The
`sessions/` directory is created on demand (like `mailbox/<machine>/`) and is intentionally **not** part
of the scaffolded `SUBDIRS` — there is nothing to seed, and it isn't part of the portable skeleton.

Messages themselves reuse the existing mailbox: `mailbox/<identity>/<stamp>--from-<identity>.md`. Nothing
about the on-disk message format changes; same-PC and cross-machine mail are the same files, just with
session-scoped names instead of hostnames.

---

## Security & robustness

- **Traversal-proof names.** A session name becomes a filename *and* a mailbox path, so it is validated
  against `[A-Za-z0-9][A-Za-z0-9._-]*` — no `/`, no `..`, no leading separator. An illegal name is
  rejected at the boundary with a clear error and nothing is written.
- **A corrupt or foreign presence file never breaks a listing.** Every read collapses parse/IO failures
  to "skip this record," so one bad file can't take down `session ls`, `broadcast`, or `prune`.
- **No auto-deletion of mail.** Broadcast only *writes*; pruning only removes *presence* files, never
  messages. Reading mail is still the explicit, non-destructive `inbox [--read]`.

---

## Command surface (summary)

| Command | Purpose |
|---|---|
| `export CAIRN_MACHINE=<name>` | Give this shell/session its own mailbox identity |
| `cairn session start [name]` | Register / heartbeat a session in the roster |
| `cairn session ls` | List this machine's sessions with live/stale presence |
| `cairn session whoami` | Show resolved identity + its source |
| `cairn session end [name]` | Remove a session from the roster |
| `cairn session prune` | Remove sessions not seen within the staleness window |
| `cairn send <name> "<msg>"` · `cairn inbox` | One-to-one message to a session (unchanged commands) |
| `cairn broadcast "<msg>"` | One-to-many message to every other live session |

---

## Future waves (not yet built)

Tracked in [BACKLOG.md](BACKLOG.md); listed here so the design intent is on record:

- **Inbox surfacing at SessionStart** — have the hook mention unread count/preview so a session *notices*
  mail without polling `inbox`. (The hook must still never break a session — additive, best-effort.)
- **Blocking wait** — `cairn inbox --wait [--timeout N]` to await a reply (poll loop), for turn-taking.
- **Auto-heartbeat** — optionally refresh `last_seen_utc` on any command so presence is accurate without
  explicit `session start`, weighed against adding a write to read-only commands.
- **Threaded replies** — carry a conversation id so `inbox` can group a back-and-forth.
