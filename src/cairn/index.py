"""Full-text search over the vault (``cairn recall``) — the SQLite-FTS payoff from RESEARCH.md §4.

Files stay the source of truth; the index is a throwaway. At personal scale we build an in-memory
SQLite FTS5 table from the markdown on each query — no persistent index to go stale, no dependency
beyond the stdlib ``sqlite3`` (FTS5 ships with it). If FTS5 is somehow unavailable, we fall back to
a substring scan so ``recall`` still works, just without BM25 ranking.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from cairn.vault import Vault


@dataclass(frozen=True)
class SearchHit:
    """One match: which store it came from, its name, and a highlighted snippet."""

    kind: str  # "memory" | "note"
    name: str
    snippet: str


def _documents(vault: Vault) -> list[tuple[str, str, str]]:
    """(kind, name, body) for every memory and session note in the vault."""
    docs: list[tuple[str, str, str]] = []
    if vault.memories_dir.is_dir():
        for path in sorted(vault.memories_dir.glob("*.md")):
            docs.append(("memory", path.stem, path.read_text()))
    if vault.session_notes_dir.is_dir():
        for path in sorted(vault.session_notes_dir.glob("*.md")):
            docs.append(("note", path.stem, path.read_text()))
    return docs


def _fts_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (quoted terms, AND-ed)."""
    terms = re.findall(r"\w+", query.lower())
    return " ".join(f'"{term}"' for term in terms)


def _substring_fallback(
    docs: list[tuple[str, str, str]], query: str, limit: int
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    needle = query.lower()
    for kind, name, body in docs:
        idx = body.lower().find(needle)
        if idx != -1:
            start = max(0, idx - 20)
            hits.append(SearchHit(kind, name, body[start : idx + len(query) + 40].strip()))
    return hits[:limit]


def search(vault: Vault, query: str, *, limit: int = 10) -> list[SearchHit]:
    """Return the best ``limit`` matches for ``query`` across memories + session notes."""
    docs = _documents(vault)
    match = _fts_query(query)
    if not match or not docs:
        return []

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE docs USING fts5(kind, name, body)")
        conn.executemany("INSERT INTO docs(kind, name, body) VALUES (?, ?, ?)", docs)
        rows = conn.execute(
            "SELECT kind, name, snippet(docs, 2, '>>', '<<', '…', 12) "
            "FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
            (match, limit),
        ).fetchall()
        return [SearchHit(kind, name, snippet) for kind, name, snippet in rows]
    except sqlite3.OperationalError:
        return _substring_fallback(docs, query, limit)
    finally:
        conn.close()
