"""Delegation workers — the cheaper model targets the driver hands sub-tasks to, to save budget.

One registry (``[[worker]]`` in cairn.toml), two backends:

- ``claude`` — materialized as a Claude Code subagent at ``.claude/agents/cairn-<name>.md`` whose
  ``model:`` frontmatter pins the tier (e.g. sonnet/haiku). The driver delegates to it with the
  Task tool, so heavy sub-tasks run on a cheaper model instead of the primary (expensive) one.
- ``local`` — an Ollama-style model called over HTTP; run with ``cairn workers run <name> "..."``.

Subagent files are *generated* from config + a shared operating-rules template, so adding a worker
is pure config and every worker enforces the same "you are a budget-saving delegate" contract. This
keeps the two backends behind one abstraction: a worker is data; the backend decides how it runs.
"""

from __future__ import annotations

from pathlib import Path

from cairn.config import WorkerConfig
from cairn.delegate import PostFn, _default_post
from cairn.errors import CairnError

#: Generated subagents are namespaced so ``install`` only ever rewrites Cairn's own files and never
#: clobbers a hand-authored agent that happens to share a name.
AGENT_PREFIX = "cairn-"

_OPERATING_RULES = (
    "You are **{name}**, a worker subagent. The primary (more expensive) model delegated a "
    "well-scoped sub-task to you specifically to preserve its own context and budget. Do the task "
    "completely and return a compact, high-signal result — you are not here to converse.\n"
    "\n"
    "Operating rules:\n"
    "\n"
    "- Do exactly the task described. If inputs are ambiguous, make the most reasonable "
    "assumption, state it in one line, and proceed — don't stall to ask.\n"
    "- Read the raw material yourself (open files, run commands). The point is that bulky inputs "
    "live in *your* context, not the driver's — never ask the driver to paste what you can open.\n"
    "- Return only what was asked for, in the shape requested. Lead with the answer; keep it "
    "tight.\n"
    "- Correctness over brevity: say exactly which files you changed or what you found. Don't "
    "pad.\n"
    "- You are not the driver: don't expand scope, refactor unrelated code, or make product or "
    "architecture decisions — surface those back for the driver to decide.\n"
    "\n"
    "Your assignment: {role}\n"
)


def agent_name(worker: WorkerConfig) -> str:
    """The Claude Code subagent name/filename stem for a worker (``cairn-<name>``)."""
    return f"{AGENT_PREFIX}{worker.name}"


def render_claude_agent(worker: WorkerConfig) -> str:
    """Render the full ``.md`` subagent definition for a ``claude``-backend worker.

    Frontmatter pins ``model:`` to the worker's tier; the body is the shared delegate contract with
    the worker's ``role`` spliced in. Pure — no I/O — so the exact output is unit-tested.
    """
    name = agent_name(worker)
    role = worker.role or "well-scoped sub-tasks the driver hands off to save budget"
    frontmatter = (
        "---\n"
        f"name: {name}\n"
        f"description: {role} (cairn delegation worker on {worker.model} — the driver hands it "
        "heavy or mechanical sub-tasks to preserve the primary model's budget.)\n"
        f"model: {worker.model}\n"
        "---\n\n"
    )
    return frontmatter + _OPERATING_RULES.format(name=name, role=role)


def install_claude_workers(workers: tuple[WorkerConfig, ...], agents_dir: Path) -> list[Path]:
    """Write ``cairn-<name>.md`` for every ``claude``-backend worker into ``agents_dir``.

    Idempotent and non-destructive: only ``cairn-<name>.md`` files are (re)written; any other agent
    in the directory is left untouched. ``local`` workers are skipped (they run over HTTP, not as
    subagents). Returns the installed paths, sorted.
    """
    agents_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    for worker in workers:
        if worker.backend != "claude":
            continue
        dest = agents_dir / f"{agent_name(worker)}.md"
        dest.write_text(render_claude_agent(worker))
        installed.append(dest)
    return sorted(installed)


def run_local_worker(worker: WorkerConfig, prompt: str, *, post: PostFn = _default_post) -> str:
    """Run a ``local``-backend worker's model over HTTP and return the generated text.

    Raises :class:`CairnError` for a non-local worker (those run as Claude subagents via the Task
    tool, not over HTTP). ``post`` is injected so the URL + payload are asserted without a server.
    """
    if worker.backend != "local":
        raise CairnError(
            f"worker {worker.name!r} is a '{worker.backend}' worker — delegate to it via the Task "
            f"tool as subagent '{agent_name(worker)}', not `workers run`"
        )
    url = worker.endpoint.rstrip("/") + "/api/generate"
    data = post(url, {"model": worker.model, "prompt": prompt, "stream": False})
    return data.get("response", "")
