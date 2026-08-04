# Generic Primitives — Research & Strategy (2026-08)

*Deep-research synthesis (fan-out web search → adversarial verification → cited report). Goal: find
high-level, generic feature primitives cairn could add that serve **both** solo operators / small
businesses (the "3D-print-farm owner who runs his shop with Claude") **and** power users/devs —
without verticalizing. Method, caveats, and sources are at the bottom.*

---

## TL;DR — the strategic thesis

**cairn's moat is architectural, not feature-novelty.** Almost every generic capability people want
(task continuity, model routing, orchestration, observability) *already exists* — but every incumbent
delivers it with the exact infrastructure cairn refuses: MCP servers, event-sourced databases, or
port-binding daemons. cairn's edge is that it does these as **plain files in a portable, synced
vault, no daemon/ports/admin, with Claude as the driver.**

So the play is **not** to out-feature anyone. It's to own the **local-first, no-infra version** of
four generic problems, and to lean into the reliability evidence that favors a single human/Claude
driver over autonomous agent swarms.

Concretely: **don't** compete on generic packaging (Anthropic's own plugin system owns that). **Do**
build memory-that-governs-the-next-action, no-infra observability, compounding memory, and
checkpoint-based delegation.

---

## 1. Landscape — what already exists

- **First-party packaging is table-stakes, not a moat.** Anthropic's plugin system bundles slash
  commands, subagents, MCP servers, and hooks into one installable unit (via `/plugin`, across
  terminal + VS Code), and is explicitly positioned as "our standard way to bundle and share Claude
  Code customizations," including team-guardrail consistency. [1][4] → cairn's *profiles* shouldn't
  try to beat this; their edge is living in a **portable synced vault that follows you across
  machines with no marketplace/install step**, toggled per-project.
- **The field is mature and categorized.** A ~1.9k★ community "awesome-claude-plugins" list already
  organizes the ecosystem into nine functional categories. Cross-session task management (`backlog`)
  and multi-agent orchestration (`maestro-orchestrate`, 22+ subagents / 4-phase workflows) are
  **established, contested** categories — but `backlog` stores state in an MCP server + event-sourced
  DB (optionally S3), and orchestrators are server/subagent-heavy. [2] **This is the seam:** they
  solve real generic problems via exactly the daemon/DB/server architecture cairn's Tier-0 DNA rules
  out.
- **"Auto-route to cheap models" is contentious for a reason.** The canonical tool, `claude-code-
  router`, is a **local background gateway/daemon** binding `127.0.0.1:3456` (+ `:3458` UI) that
  routes across 8+ providers for cost — and the documented trade-off is "you keep Claude Code's UX,
  not Claude": cheap models break agentic multi-step reasoning. [2][3] Separately, an **April-2026
  policy change** revoked OAuth so Claude *subscriptions* stopped working with third-party harnesses;
  only Anthropic-official tooling keeps subscription access. [3] → cairn's config-driven, no-daemon
  delegation (cheap subagents + local Ollama) is the *differentiated, safe* take: no gateway, Claude
  stays the driver, official-tool-aligned.
- **Reliability evidence favors "Claude stays the driver."** Across a controlled comparison, a single
  agent succeeded 28/28 while hierarchical / stigmergic-swarm / gated-pipeline multi-agent structures
  failed **36% / 68% / 100%**; the pattern that works is "**discrete, well-scoped modules chained via
  deterministic handoffs and human checkpoints** — not true collaboration." [5] Anthropic's own
  **Project Vend** corroborates the guardrail need: an unsupervised agent running a real shop lost
  money ($1,000 → under $800 in a month). [6] And Agent Teams (peer messaging) is experimental,
  flag-gated, and burns 3–7× tokens. [4]

**Already well-served (don't chase):** packaging/marketplace, server-backed task DBs, port-daemon
model routing, dashboard observability, autonomous multi-agent swarms.

---

## 2. The gaps cairn is uniquely positioned to own

The white space is the **local-first / no-infrastructure version** of four generic problems:

| # | Generic gap | Why it's open for cairn |
|---|---|---|
| G1 | **Memory-as-governance** — stop the agent from repeating known-bad actions | Incumbents *store* memory; none *act on the next action* locally |
| G2 | **No-infra observability** — "what did my agents actually do?" | Answered today only by always-on dashboards w/ DBs + ports |
| G3 | **Compounding memory** — session notes that consolidate into durable memory | cairn's checkpoints hand off once; they don't yet accumulate |
| G4 | **Reliable delegation** — offload bulk work without swarm fragility | Evidence says chained modules + checkpoints beat autonomous agents |

---

## 3. Proposed primitives (ranked)

### RANK 1 — Pre-action guardrail gate *(high impact · medium effort)*  → G1

**Generic problem:** agents repeat previously-failed fixes and edit known-fragile files. cairn ships
a **deterministic, history-derived lookup** (no LLM call, no embeddings) that warns or blocks *before*
the risky action — "memory that acts on the agent's next action rather than merely answering." [7]

- **Print-farm:** warn before re-running a slicer/G-code tweak that already caused failed prints, or
  before editing a printer-profile file flagged fragile.
- **Power-user:** warn before re-attempting a fix that already broke CI, or editing a file with a
  history of regressions.
- **Tier-0 mechanism:** distill the vault's own messages/checkpoints/logs into a `fragile-files` +
  `failed-attempts` index (plain JSON/Markdown), enforced via a Claude Code **pre-tool-use hook** that
  greps the index and warns/blocks. Fully local, grep-able, git-native. [7]
- **Differentiation:** incumbents store or route; **none govern the next action locally.** Unoccupied,
  squarely in cairn's DNA (vault + hooks).
- **Open Qs:** hook *blocking* vs *warning* semantics; keeping "Claude stays the driver" while
  enforcing a block.

### RANK 2 — Local-first agent activity log / observability *(high impact · low–med effort)*  → G2

**Generic problem:** "what did the agent(s) actually do across my sessions/machines?" is answered
today only by dashboards with databases and open ports. cairn answers it with **files, no infra.**

- **Print-farm:** a durable, greppable trail of what each shop session changed (pricing script,
  inventory note, print-queue decision), reviewable later on any machine.
- **Power-user:** a diff-able, PR-reviewable record of every agent decision/fix, versioned by git, for
  auditing multi-session work.
- **Tier-0 mechanism:** an **append-only, plain-text event log** of typed events
  (`issue`/`attempt`/`fix`/`decision`/`note`) written to the vault via write-hooks; `cairn log`
  greps/tails it. No vector DB, no daemon. [7]
- **Differentiation:** turns cairn's existing messaging/checkpoint files into a queryable audit trail
  with zero daemon — a portability story no port-binding dashboard can match.
- **Framing caveat:** pitch as *"cairn owns the no-infra observability niche,"* **not** "nobody does
  observability" (the strong version was refuted — see below).

### RANK 3 — Memory consolidation + warm-start *(high impact · medium effort)*  → G3

**Generic problem:** session memory decays and duplicates; cairn's checkpoints should **compound into
durable memory**, not just hand off once.

- **Print-farm:** shop preferences / customer notes / pricing rules consolidate into a stable profile
  that warm-starts every session on any machine.
- **Power-user:** coding conventions and hard-won gotchas merge into project memory instead of being
  re-derived each session.
- **Tier-0 mechanism:** a **local-first state object** — YAML frontmatter (structured fields) +
  Markdown memory list (unstructured) — reinjected at session start and after context trimming, with
  an **end-of-session consolidation** step (run as a CLI/hook, not a server) that merges session notes
  into global memory, resolves conflicts, and de-dupes. This is OpenAI's *own* recommended local-first
  pattern. [8]
- **Differentiation vs cairn today:** checkpoints are per-handoff snapshots; consolidation makes memory
  **durable and de-duplicated** across many sessions/machines — all plain vault files.
- **Open Qs:** token/latency budget of reinjecting a growing state object; when to summarize/prune.

### RANK 4 — File-based delegation/orchestration with checkpoints *(medium impact · low effort · high strategic-fit)*  → G4

**Generic problem:** users want to offload bulk work **without** the fragility of agent swarms. cairn's
delegation registry should orchestrate via **deterministic handoffs + human/driver checkpoints (vault
files)**, keeping Claude the driver — explicitly **not** autonomous peer collaboration.

- **Print-farm:** delegate bulk, well-scoped tasks (batch-relabel STL files, summarize order emails) to
  a cheap local worker; owner/Claude assembles results at a checkpoint.
- **Power-user:** chain scoped subagents (`lint → test-summarize → draft PR notes`) via files, each a
  discrete module, human checkpoint between phases.
- **Tier-0 mechanism:** extends the existing worker registry — phases as vault files, explicit
  checkpoints between them; no autonomous inter-agent chatter.
- **Differentiation:** this **is** the empirically-validated orchestration model (chained modules +
  checkpoints beat swarms [5][6]), at zero token/infra overhead — a deliberate *non*-feature (no
  swarm) as much as a feature.

---

## 4. Open questions to resolve before building

1. **Sync/conflict semantics.** When the same vault is edited on two machines (Syncthing/git), how do
   consolidation merges, the fragile-files index, and the append-only log resolve concurrent writes
   *without a server*? Append-only + last-writer-wins may be insufficient for the guardrail index.
2. **Hook blocking semantics.** How exactly does a pre-tool-use hook block vs warn (exit codes), and
   can it *enforce* a block while preserving "Claude stays the driver"?
3. **Warm-start budget.** Token/latency cost of reinjecting a growing consolidated state at every
   session start; at what vault size does it need summarization/pruning?
4. **Delegation routing heuristic.** Where's the line between "delegate bulk to a cheap/local worker"
   (safe) and "needs Claude's agentic reasoning" — a practical heuristic that avoids the
   cheap-model-breaks-reasoning failure mode *without* becoming a routing daemon?

---

## 5. Method, caveats & sources

**Method:** 5 search angles → 21 sources fetched → 98 claims extracted → 25 adversarially verified
(2-of-3 vote to kill) → 21 confirmed, 4 refuted → 7 synthesized findings.

**Caveats (read before acting):**
- Strongest primitives (guardrail gate, event-log observability, memory consolidation, warm-start)
  rest on **primary** sources — ProjectMEM (arXiv:2606.12329) and OpenAI's cookbook — and are
  high-confidence. Landscape/competitive claims lean partly on a community list + product blogs, but
  are corroborated by Anthropic's primary docs.
- **Time-sensitivity is real:** `/plugin` is public beta, Agent Teams is experimental/flag-gated, and
  the April-2026 third-party-OAuth cutoff is a live policy. cairn must stay Anthropic-official-aligned
  (it is).
- The **28/28 single-agent** figures are from *one* non-peer-reviewed preprint (one task, one model,
  $50 budget). Treat the *direction* (single-driver > autonomous swarm) as well-supported; the exact
  percentages as one experiment, not a law.
- Two claims were **refuted** and shaped framing: "orchestration" isn't a literal awesome-list
  category, and the strong "all observability tooling is a server" claim was killed (0-3) — so the
  observability pitch is *"we own the no-infra niche,"* not *"nobody does observability."*

**Key sources:**
[1] Anthropic — Claude Code plugins (primary) · https://claude.com/blog/claude-code-plugins
[2] awesome-claude-plugins (community list) · https://github.com/composio-community/awesome-claude-plugins
[3] claude-code-router (primary) · https://github.com/musistudio/claude-code-router · pricing/policy: https://www.productcompass.pm/p/claude-code-pricing
[4] Claude Code extensions explained (blog) · https://pub.towardsai.net/claude-code-extensions-explained-skills-mcp-hooks-subagents-agent-teams-plugins-9294907e84ff
[5] "True multi-agent collaboration doesn't work" (CIO) · https://www.cio.com/article/4143420/true-multi-agent-collaboration-doesnt-work.html
[6] Project Vend (TIME) · https://time.com/7298088/claude-anthropic-shop-ai-jobs/
[7] ProjectMEM — memory-as-governance, append-only local log (arXiv, primary) · https://arxiv.org/pdf/2606.12329
[8] OpenAI cookbook — local-first state object + consolidation (primary) · https://developers.openai.com/cookbook/examples/agents_sdk/context_personalization
