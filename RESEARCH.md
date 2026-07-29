# Cairn — Competitive Research & Design Lessons

Notes from looking at existing tools in Cairn's neighborhood — **not to copy**, but to learn what
works, what people complain about, and where Cairn can do better. Each section ends with the concrete
decision it drives. (Dated 2026-07-29.)

---

## 1. Model routers — `claude-code-router` (musistudio)

**What it is:** a local **proxy**. You launch `ccr code` instead of `claude`; it intercepts Claude
Code's requests, rewrites them to any provider's format (DeepSeek/Qwen/GLM/Gemini/local), and routes
*by request scenario* — `default`, `background`, `reasoning`, `longContext` (past a ~60k-token
threshold), `webSearch`. Config in `~/.claude-code-router/config.json`.

**What people say / complain about:**
- Value: escape Anthropic-only limits, use free models for trivial tasks, cost control.
- Pain: **config overhead**, correct provider setup is fiddly, it's a community project (not official),
  and it is **not a clean replacement** for Claude Code's login/policy/support/reliability path — it
  sits in front of and *replaces* the launch path.

**Lessons for Cairn:**
- **Do NOT be a proxy.** The proxy model is powerful but heavyweight and it hijacks the login/support
  path — exactly the "unwillingness to install / too invasive" problem we're avoiding. Cairn stays
  **additive**: Claude remains the driver; `cairn ask` delegates *specific bulk subtasks* to local
  Ollama. ccr is complementary, not a competitor.
- **Config overhead is the #1 complaint** → validates our principle: one small TOML, few knobs.
- Their scenario buckets (background/reasoning/long-context) are a good vocabulary for *explicit*
  routing rules if we ever expand delegation beyond "bulk mechanical work."

## 2. Memory servers — Basic Memory vs Mem0

**Basic Memory (MCP):** local-first, stores everything as **plain Markdown** you can also open in your
editor — "human-readable, diff-friendly, **no opaque database**." Agent reads/appends markdown across
sessions.

**Mem0 (MCP):** **semantic/vector** memory, managed service, `search_memories`/`add_memory` tools,
syncs across machines, retrieves the right context mid-task. Heavier; hosted store.

**Lessons for Cairn:**
- Cairn belongs firmly in the **Basic Memory camp**: files as source of truth, no proprietary DB, no
  hosted service. That's the dependency-light, sync-friendly, user-trust-friendly choice.
- Mem0's edge is *semantic retrieval* + *cross-machine*. Cairn gets cross-machine from plain file sync
  (no service), and can add semantic recall later **without** a hosted dep (see §4).

## 3. Obsidian second-brain plugins (Smart Connections et al.)

**How they index:** chunk each note (with overlap) → embed each chunk (commonly **nomic-embed-text**)
→ store vectors locally → cosine similarity for "related notes." Best ones use a **hybrid**: BM25
keyword + embedding rerank, so you get exact hits *and* meaning-based ones. Local embedding model =
zero setup, no API key, data stays on device.

**Lessons for Cairn:**
- Obsidian is a **human note UI** — not our lane (don't build note-editing UI). But its *retrieval*
  architecture is the reference for our `cairn recall` (icebox #5.5): hybrid keyword + local embeddings.
- `nomic-embed-text` is the community-standard local embedder and the user **already runs it** (Mac
  Mini, per DataLens). So semantic recall costs no new dependency and no API key.

## 4. Organization & fast lookup — the "KV / nosql, but limit dependency" question

**The pain (validated):** Claude Code has only global (`~/.claude/CLAUDE.md`) and per-project memory,
with **no shared-across-a-*subset*-of-projects** option. Users duplicate memory into each project or
dump it in global — both go stale/noisy. This is an **acknowledged, open feature request**
([#36561](https://github.com/anthropics/claude-code/issues/36561),
[#39195](https://github.com/anthropics/claude-code/issues/39195)); the community's own proposed fix is
"configurable shared memory paths / named memory namespaces" — **exactly Cairn's profiles + vault.**

**The lookup decision:**
- **Source of truth = Markdown files in the vault.** Human-readable, diff-friendly, git/sync-friendly,
  no opaque DB. (This is what people *like* about Basic Memory and *distrust* about vector services.)
- **Fast lookup = a rebuildable index built _from_ the files — using stdlib SQLite.** Python ships
  `sqlite3`; SQLite's **FTS5** gives BM25-ranked full-text search with **zero added dependencies**
  ("you don't need anything else"). This is the "KV / nosql" the user wanted, for free. The DB is a
  **cache, not the master**: delete it and re-scan the vault to rebuild. Markdown is truth; SQLite is speed.
- **MVP stays even simpler:** at personal scale (tens–hundreds of files) a direct directory scan +
  small JSON manifest is enough. SQLite FTS is introduced only when `recall`/search lands (icebox), so
  we never carry complexity (or a schema) before it earns its place.
- **Semantic recall (later):** embeddings via the already-present `nomic-embed-text`, vectors stored as
  blobs in the *same* SQLite file, hybrid BM25 + cosine. Still zero new dependencies.

## 5. Where Cairn does better (the honest scorecard)

| Need | Native Claude Code | Router (ccr) | Mem0 | Basic Memory | **Cairn** |
|---|---|---|---|---|---|
| Share memory/skills across a *subset* of projects | ❌ (open request) | — | partial | manual | ✅ **profiles** |
| Toggle bundles on/off per project | ❌ | — | ❌ | ❌ | ✅ |
| Cross-machine, **no hosted service** | ❌ (auto-mem is machine-local) | — | ✅ (hosted) | ❌ | ✅ (file sync) |
| Files as source of truth, no opaque DB | ✅ | — | ❌ | ✅ | ✅ |
| Local-model delegation without replacing the login path | ❌ | ❌ (proxy) | — | — | ✅ (`cairn ask`) |
| Dependency-light (stdlib index) | — | ❌ | ❌ | ~ | ✅ (sqlite/json stdlib) |

**Net:** Cairn's defensible position is the **intersection** nobody else occupies — toggleable
cross-project bundles + cross-machine via plain files + additive local delegation — built on
blessed primitives, files-as-truth, and a zero-dependency stdlib index.

---

### Sources
- claude-code-router: <https://github.com/musistudio/claude-code-router>, <https://www.datacamp.com/tutorial/claude-code-router>, <https://evolink.ai/blog/claude-code-with-openrouter-limits-errors-alternatives>
- Basic Memory: <https://mcpservers.org/servers/basicmachines-co/basic-memory> · Mem0: <https://mem0.ai/blog/claude-code-memory>
- Obsidian second-brain / Smart Connections: <https://community.obsidian.md/plugins/smart-second-brain>, <https://github.com/rahilp/second-brain-obsidian-plugin>
- Shared-memory feature requests: <https://github.com/anthropics/claude-code/issues/36561>, <https://github.com/anthropics/claude-code/issues/39195>
- SQLite FTS5 in Python stdlib: <https://docs.datasette.io/en/stable/full_text_search.html>, <https://abdus.dev/posts/quick-full-text-search-using-sqlite/>
