# Contributing to Cairn

Thanks for helping out! Cairn aims to be a small, dependency-light, thoroughly-tested tool. A few
things keep it that way.

## Getting set up

Requires **Python 3.11+** (for stdlib `tomllib`).

```bash
git clone https://github.com/JacobAYoung/cairn.git && cd cairn
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest          # run the suite (should be all green)
ruff check .    # lint
cairn --version
```

## Where things live

- Code: `src/cairn/` — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for what each module does and
  how they connect.
- Tests: `tests/test_<module>.py` (one per module).
- Design & roadmap: [docs/SPEC.md](docs/SPEC.md), [docs/BACKLOG.md](docs/BACKLOG.md).
- The engineering standard every change must meet: [CLAUDE.md](CLAUDE.md).

## The bar for a change

1. **Read [CLAUDE.md](CLAUDE.md).** It's the non-negotiable standard (SOLID/seams, docs, AAA tests,
   security). New behavior that doesn't meet it won't merge.
2. **Every new/changed module gets tests** that assert *exact data* in/out **and** the interactions
   (call count + payload) for each external call — not just "it ran." Use real temp dirs, not
   filesystem mocks. Cover a failure/edge case, not only the happy path.
3. **Keep it dependency-light.** The only runtime dep is `httpx`. Prefer the standard library
   (`tomllib`, `sqlite3`, `subprocess`, `json`) before adding anything.
4. **Stay reversible and non-destructive.** Anything that writes to a user's project or `~/.claude`
   must be manifest-tracked and undoable, and must never clobber a hand-placed file.
5. **Green before you push:** `ruff check .` and `pytest` both pass.

## Workflow

- Branch off `main`, make the change with tests, open a PR. CI runs ruff + pytest on 3.11–3.13.
- Keep commits focused; explain the *why* in the message.
- Scope check for new features: *does this strengthen the bundle-toggle or the cross-machine story?*
  If not, it probably belongs in the icebox (see [docs/BACKLOG.md](docs/BACKLOG.md)) or nowhere.

## Releases

Releases are cut from tags by CI (see [.github/workflows/release.yml](.github/workflows/release.yml)):

1. Bump `__version__` in `src/cairn/__init__.py`, note the change in `docs/BACKLOG.md`.
2. Commit, then tag: `git tag -a vX.Y.Z -m "…" && git push origin main --tags`.
3. The release workflow builds the wheel + sdist and publishes a GitHub Release with them attached.
