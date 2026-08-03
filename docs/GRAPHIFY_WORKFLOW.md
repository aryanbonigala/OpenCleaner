# Graphify Workflow for OpenCleaner

How agents working on OpenCleaner should use the graphify knowledge graph.

## 1. Purpose

OpenCleaner is large enough that rereading it per task is slow and expensive.
Graphify keeps a persistent local knowledge graph of this repo so an agent can
locate the relevant subsystem, safety rules and past decisions in a few hundred
tokens instead of loading half the codebase.

The graph is a **map, not the territory**. It tells you where to look and what was
decided. The repo is the source of truth for what the code actually does.

- Graph data lives in `graphify-out/` at the repo root (git-ignored, local only).
- Curated project facts live in `docs/PROJECT_GRAPH_FACTS.md` and are extracted into the graph.
- `.graphifyignore` keeps tooling noise (`.claude/`, `.serena/`, build output) out of the graph.

## Setup (once per clone)

The graph and the assistant skill are machine-local and deliberately not committed —
the generated hooks embed absolute paths that only work on the machine that made them.

```bash
uv tool install "graphifyy[sql]"   # the [sql] extra is required, see below
graphify install --project         # registers the /graphify skill for this repo
```

Then build the graph once: run `/graphify .` from your AI assistant. Without the `[sql]`
extra, `backend/sql/schema.sql` silently contributes nothing and the DB tables are
missing from the graph.

## 2. When to query Graphify

Query it when you need orientation:

- "Where does X live?" / "What touches Y?"
- "What was decided about Z, and why?"
- "What are the safety rules around this area?"

Do **not** query it for:

- The current contents of a file — read the file.
- Anything you already have in context.
- Trivial single-file edits where you already know the path.

## 3. What to query before each task

Run these before writing code:

1. The relevant subsystem, to find the files that matter.
2. The safety invariants that govern the area you are about to touch.
3. Recent decisions touching the files you plan to edit.
4. Known risks and unresolved TODOs in that area.

Then open the actual files. **If the graph and the code disagree, the code wins.**

## 4. What to write after each task

Append or amend concise bullets in `docs/PROJECT_GRAPH_FACTS.md`, then refresh the graph:

```bash
graphify update .
```

Record only:

- files changed (paths, not diffs)
- new decisions and the one-line reason
- new or changed APIs
- new invariants
- bugs fixed (the root cause, one line)
- risks that remain

## 5. What never to store

Never put any of these in the graph or in `PROJECT_GRAPH_FACTS.md`:

- secrets, API keys, tokens, credentials
- personal data, real user file paths, machine-specific absolute paths
- full diffs, raw test output, long logs, pasted reports
- scan results or database contents from a real machine

## 6. How to keep graph entries concise

One fact per bullet, ideally one line, phrased so it is useful without surrounding context.

Good:

> `scan_items` row identity is `(scan_id, id)`; item ids repeat across scans but must be
> unique within one scan.

Bad:

> A 300-line paste of the commit diff.

If a fact needs a paragraph to explain, it belongs in a design doc — link to that doc
and keep the one-line summary in the facts file.

## 7. How to handle conflicting graph facts

- **Code vs graph** → code wins. Correct the graph in the same task.
- **Docs vs code** → prefer code, and note the doc drift in your final report.
- **Two graph facts conflict** → check both against code, keep the true one, move the other
  to *Superseded facts*.
- **Safety invariants conflict** → stop and ask Aryan, unless the safer reading is obvious.
  When in doubt, take the more restrictive one and flag it.

## 8. How to handle stale graph facts

Move the old bullet to the **Superseded facts** section of `docs/PROJECT_GRAPH_FACTS.md`
with `~~strikethrough~~` and a short "superseded by …" note. Do not delete history —
knowing that `scan_items` was once keyed on `id` alone explains the migration code.

If the graph itself is stale (files changed but the graph did not), rebuild:

```bash
graphify update .        # incremental, AST-only, no API cost
```

Two things to know about `graphify update .`:

- It re-extracts **code only**. Edits to `PROJECT_GRAPH_FACTS.md` and other docs are not
  picked up by it — they need a semantic pass (`/graphify --update` from inside an AI
  assistant). The curated fact nodes already in the graph are preserved by `update`, so
  running it is always safe.
- It re-clusters, so hand-written community names are replaced by hub-derived ones
  (e.g. `process_action_policy.py`). Harmless — `explain`, `path` and `query` are
  unaffected. Run `graphify label` only if you want prettier names back.

## 9. How to report Graphify updates in final agent reports

Every task that changed the graph should state, in one short block:

- facts added / amended / superseded (by name, not full text)
- whether `graphify update .` was run
- any conflict found between graph and code, and how it was resolved

---

## Query examples

Verify command syntax with `graphify --help` if unsure; these are the current forms.

**Pick the right tool — this matters for token cost.** Measured on this repo's graph
(1154 nodes): `query` is a breadth-first traversal that reaches 200–300 nodes on a
typical question and truncates against your budget. It is for *orientation* ("what
area is this?"), and should always be budgeted. `explain` and `path` return a handful
of lines and are the right tool once you know the concept you care about.

```bash
# PRECISE — a named decision, invariant or risk. Returns ~10 lines.
graphify explain "SafetyInvariant: unknown items are report-only"
graphify explain "Decision: DB retains the newest 25 scans"
graphify explain "Decision: scan_items identity is (scan_id, id)"

# PRECISE — how a decision connects to the code it governs.
graphify path "Decision: foreign keys enabled per connection" "db.py"
graphify path "Subsystem: chat command preview API" "chat_preview.py"

# ORIENTATION — always pass --budget; expect a broad subgraph.
graphify query "process execution safety invariants" --budget 900
graphify query "scan persistence retention and scan item id decisions" --budget 600
graphify query "frontend process control dashboard and FPS optimizer components" --budget 700
graphify query "files involved in process inventory and preview end" --budget 600
graphify query "known risks before adding process execution" --budget 600

# Reverse impact — what breaks if I change this?
graphify affected "prune_old_scans()"
```

The curated nodes are named with stable prefixes, so they are easy to target with
`explain`: `Subsystem: …`, `Decision: …`, `SafetyInvariant: …`, `KnownRisk: …`.

---

## Copy-paste block for future prompts

> Before coding: query graphify for the relevant subsystem, the safety invariants, recent
> decisions touching the files you will edit, and known risks. Then read the actual repo
> files — code is the source of truth if the graph disagrees.
>
> After coding: add concise facts to `docs/PROJECT_GRAPH_FACTS.md` (changed files, new
> decisions, new APIs, new tests, new invariants, bugs fixed, risks remaining), move any
> outdated fact to *Superseded facts*, then run `graphify update .`. Never store secrets,
> personal data, full diffs, or raw logs. Report what you changed in the graph.
