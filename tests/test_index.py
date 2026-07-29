"""Tests for full-text recall (:mod:`cairn.index`) against a real temp vault."""

from __future__ import annotations

from cairn.checkpoints import write_checkpoint
from cairn.index import search
from cairn.vault import Vault


def _seed(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.ensure_layout()
    (vault.memories_dir / "code-conventions.md").write_text(
        "Use pytest for tests. Prefer composition over inheritance."
    )
    (vault.memories_dir / "deploy.md").write_text("Deploys go out Fridays via the release script.")
    write_checkpoint(
        vault, "proj", "Decided to migrate the store to Postgres.", machine="box", now="T"
    )
    return vault


def test_search_finds_memory_by_term(tmp_path):
    vault = _seed(tmp_path)

    hits = search(vault, "pytest")

    assert len(hits) == 1
    assert hits[0].kind == "memory"
    assert hits[0].name == "code-conventions"
    assert "pytest" in hits[0].snippet.lower()


def test_search_finds_checkpoint_note(tmp_path):
    vault = _seed(tmp_path)

    hits = search(vault, "postgres")

    assert [(h.kind, h.name) for h in hits] == [("note", "proj")]


def test_search_ranks_and_limits(tmp_path):
    vault = _seed(tmp_path)
    # "the" appears in multiple docs; limit caps the results
    hits = search(vault, "the", limit=1)
    assert len(hits) <= 1


def test_search_no_match_returns_empty(tmp_path):
    vault = _seed(tmp_path)
    assert search(vault, "kubernetes") == []


def test_search_empty_query_returns_empty(tmp_path):
    vault = _seed(tmp_path)
    assert search(vault, "   ") == []
