"""Tests for delegation workers (:mod:`cairn.workers`): subagent render/install + local run."""

from __future__ import annotations

import pytest

from cairn.config import WorkerConfig
from cairn.errors import CairnError
from cairn.workers import (
    agent_name,
    install_claude_workers,
    render_claude_agent,
    run_local_worker,
)


def _claude(name="delegate", model="sonnet", role="do the thing"):
    return WorkerConfig(name=name, backend="claude", model=model, role=role)


def _local(name="sum", model="qwen2.5:14b", endpoint="http://localhost:11434"):
    return WorkerConfig(
        name=name, backend="local", model=model, role="summarize", endpoint=endpoint
    )


# --- rendering ------------------------------------------------------------------------------


def test_agent_name_is_namespaced(tmp_path):
    assert agent_name(_claude(name="delegate")) == "cairn-delegate"


def test_render_pins_model_and_splices_role(tmp_path):
    md = render_claude_agent(_claude(name="delegate", model="sonnet", role="search many files"))

    # Frontmatter: the subagent's model tier is exactly the worker's model
    assert "name: cairn-delegate\n" in md
    assert "model: sonnet\n" in md
    # The role appears in the description and as the assignment in the body
    assert "search many files" in md
    assert "Your assignment: search many files" in md
    # The shared delegate contract is present
    assert "You are **cairn-delegate**" in md
    assert "you are not here to converse" in md


# --- installing -----------------------------------------------------------------------------


def test_install_writes_only_claude_workers(tmp_path):
    agents = tmp_path / "agents"

    installed = install_claude_workers((_claude(name="delegate"), _local(name="sum")), agents)

    # Local worker is skipped (it runs over HTTP, not as a subagent)
    assert [p.name for p in installed] == ["cairn-delegate.md"]
    assert (agents / "cairn-delegate.md").exists()
    assert not (agents / "cairn-sum.md").exists()
    assert "model: sonnet" in (agents / "cairn-delegate.md").read_text()


def test_install_is_idempotent_and_preserves_foreign_agents(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "my-own-agent.md").write_text("hand-authored")

    install_claude_workers((_claude(name="delegate"),), agents)
    install_claude_workers((_claude(name="delegate"),), agents)  # rerun

    assert (agents / "my-own-agent.md").read_text() == "hand-authored"  # untouched
    assert [p.name for p in agents.glob("cairn-*.md")] == ["cairn-delegate.md"]  # exactly one


def test_install_returns_sorted_paths(tmp_path):
    agents = tmp_path / "agents"

    installed = install_claude_workers((_claude(name="zeta"), _claude(name="alpha")), agents)

    assert [p.name for p in installed] == ["cairn-alpha.md", "cairn-zeta.md"]


# --- local run ------------------------------------------------------------------------------


def test_run_local_posts_exact_payload_and_returns_response(tmp_path):
    calls = []

    def fake_post(url, payload):
        calls.append((url, payload))
        return {"response": "the summary"}

    text = run_local_worker(_local(model="qwen2.5:14b"), "summarize this", post=fake_post)

    assert text == "the summary"
    assert len(calls) == 1  # exactly one HTTP call
    url, payload = calls[0]
    assert url == "http://localhost:11434/api/generate"
    assert payload == {"model": "qwen2.5:14b", "prompt": "summarize this", "stream": False}


def test_run_local_strips_trailing_slash_on_endpoint(tmp_path):
    seen = {}

    def fake_post(url, payload):
        seen["url"] = url
        return {"response": ""}

    run_local_worker(_local(endpoint="http://localhost:11434/"), "x", post=fake_post)

    assert seen["url"] == "http://localhost:11434/api/generate"  # no doubled slash


def test_run_local_rejects_a_claude_worker(tmp_path):
    def fake_post(url, payload):  # pragma: no cover - must never be called
        raise AssertionError("claude workers must not be run over HTTP")

    with pytest.raises(CairnError, match="delegate to it via the Task tool"):
        run_local_worker(_claude(name="delegate"), "x", post=fake_post)
