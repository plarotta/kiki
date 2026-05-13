# kiki — Assistant Memory Wiki

This directory is a **persistent memory store** for an LLM coding assistant. Its purpose is to let the assistant accumulate knowledge about the user — their style, preferences, projects, history, and evolving persona — across sessions, so that adaptation compounds instead of resetting on every conversation.

The high-level pattern comes from the [LLM Wiki idea](https://github.com/plarotta/kiki/blob/main/desc.md). This `CLAUDE.md` is the local instantiation: it tells an assistant working in this directory how the wiki is structured and what to do with it.

## What lives here

```
~/.kiki/                      ($KIKI_HOME — override with the env var)
├── CLAUDE.md                 ← you are here; the schema
├── raw/                      ← immutable raw sources; the assistant reads but never modifies
│   ├── transcripts/          ← chat session transcripts, conversation dumps
│   ├── notes/                ← observations, facts, preferences captured in-conversation
│   └── images/               ← screenshots, diagrams, photos
├── wiki/                     ← assistant-maintained markdown; the assistant writes, the user reads
│   ├── index.md              ← catalog of every wiki page
│   ├── log.md                ← append-only chronological log
│   ├── persona.md            ← the central model of who the user is
│   ├── preferences.md        ← coding, tooling, workflow preferences
│   ├── style.md              ← communication + code style notes
│   ├── feedback.md           ← corrections, validated approaches, "don't do X" rules
│   ├── projects.md           ← active projects overview
│   ├── entities/             ← one page per distinct entity (project, tool, person, library)
│   └── concepts/             ← cross-cutting concepts the user thinks/works in
└── .state/                   ← watcher manifest, lockfile, log (gitignorable)
```

Two hard rules:

1. **`raw/` is immutable.** Read freely. Never modify or delete files there. New material arrives via `kiki capture` (or the `kiki-capture` skill / MCP tool).
2. **`wiki/` is owned by the assistant.** The user reads it but does not hand-edit in normal operation. Edits are authoritative — date them and log them.

## Page conventions

Every wiki page starts with YAML frontmatter:

```yaml
---
title: <page title>
type: persona | preferences | style | feedback | project | entity | concept | source-summary
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [<relative-path-to-raw-source>, ...]   # optional; only for pages derived from raw/
confidence: low | medium | high                 # how sure are we
tags: [tag1, tag2]
---
```

After frontmatter:
- **H1** is the page title.
- **First paragraph** is a one-sentence summary the index can quote.
- **Body** uses standard markdown.
- **Links** between wiki pages use Obsidian-style `[[wikilinks]]` (e.g., `[[persona]]`). Wikilinks pointing to nonexistent pages are valid — they mark something worth writing later.
- **Citations to raw sources** use markdown links with the relative path: `[2026-05-12 note](../raw/notes/2026-05-12-foo.md)`.

Keep pages **small and focused**. If a page exceeds ~300 lines, split it.

## Workflows

### Ingest

When the watcher (or a human) asks you to ingest a file from `raw/`:

1. **Read** the raw source end-to-end. The **Signal** section (if present) tells you what the entry is for and where it should be filed — start there.
2. **Update existing pages** that this source informs — `persona.md`, `preferences.md`, relevant entities. Prefer updating to creating.
3. **Create new pages** only when the source introduces a distinct entity or concept that doesn't fit elsewhere.
4. **Flag contradictions**: if the new source contradicts an existing claim, do *not* silently overwrite. Note both, mark the older claim as superseded with a date, and surface the conflict in `log.md`.
5. **Update `index.md`** with any new pages or changed summaries.
6. **Append to `log.md`** with `## [YYYY-MM-DD] ingest | <title>`.
7. **Re-index qmd**: `qmd update`.
8. **Flip the source's frontmatter** `ingested: false` → `ingested: true` so the watcher knows it's done.

### Query

When the user asks a question against the wiki:

1. Start with `wiki/index.md` to find candidate pages.
2. For fuzzier queries, use `qmd query wiki "<question>"` (hybrid BM25+vector+rerank). MCP-aware agents have this as a native tool via `qmd mcp`.
3. Read the relevant pages in full before answering. Cite them inline: "see [[preferences]]".
4. If the answer involved real synthesis (a new comparison, a discovered pattern), **offer to file it back** as a new wiki page so the insight compounds.

### Lint

On request (or after every ingest batch), health-check the wiki. Look for:

- **Contradictions** between pages — same claim, different values.
- **Stale claims**: pages with `updated:` more than ~3 months old that newer sources may have invalidated.
- **Orphan pages**: no inbound `[[wikilinks]]`. Either link them in or delete.
- **Dangling links**: `[[wikilinks]]` to nonexistent pages — decide whether to create them or remove the reference.
- **Concept inflation**: pages mentioning a named concept/entity ≥3 times without that entity having its own page.
- **Index drift**: pages that exist but aren't in `index.md`, or index entries pointing to deleted pages.

Fix safe issues yourself (dangling links, missing index entries). For anything requiring judgment (deleting orphans, resolving contradictions), report and skip.

### Self-update

If you are an interactive assistant working with the user (not the watcher), capture-worthy material flows the other direction: when the user reveals a preference, gives a correction, validates an approach, or shares a fact about themselves, write it to `raw/notes/` using `kiki capture` (or the `kiki-capture` skill / MCP tool). The watcher will then ingest it into the structured wiki.

## log.md format

Append-only. Each entry starts with `## [YYYY-MM-DD] <kind> | <short title>` on its own line. Valid kinds:

- `ingest` — processed a new raw source
- `query` — answered a notable question
- `lint` — ran a health check
- `update` — direct wiki edit not tied to ingest
- `observation` — captured signal in-conversation, not yet filed elsewhere

`grep "^## \[" wiki/log.md | tail -10` gives a recent activity summary.

## index.md format

Grouped by section. Each entry: `- [[page-name]] — one-line summary` (≤120 chars). Sections in this order:

1. Core (persona, preferences, style, feedback, projects)
2. Entities (alphabetical)
3. Concepts (alphabetical)
4. Source summaries (date-descending)

## Automation: capture → watcher → ingest → lint

```
agent ──`kiki capture`──▶ $KIKI_HOME/raw/notes/foo.md
                              │
                       (launchd WatchPaths)
                              │
                              ▼
                       lib/watch-ingest.sh
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
         claude -p "ingest"        claude -p "lint"
                 │                         │
                 └─────► wiki/* + log.md + qmd update
```

**Capture.** Agents invoke the `kiki-capture` Claude Code skill, the `kiki` MCP tool, or `kiki capture` from any shell. The result is a markdown file in `raw/notes/` or `raw/transcripts/` with frontmatter, a **Signal** section (the 1–2 line hint that tells the ingestor what this is for), and the body.

**Watcher.** A launchd agent (`com.kiki.watcher`) watches `$KIKI_HOME/raw/{notes,transcripts}`. On any change it runs `lib/watch-ingest.sh`, which (a) reads `$KIKI_HOME/.state/processed.txt` to find new files, (b) invokes `claude -p` per file to run the ingest workflow above, (c) runs a single lint pass, (d) appends processed paths to the manifest. A flock prevents overlapping runs. Logs go to `$KIKI_HOME/.state/watcher.log`.

**Headless permissions.** The watcher uses `--dangerously-skip-permissions` because launchd cannot answer interactive prompts. Scope is limited to this directory.

## qmd usage

The wiki is registered as a qmd collection named `wiki`. From an interactive session:

```bash
qmd update                              # re-index after edits
qmd search wiki "<keyword>"             # BM25 keyword
qmd vsearch wiki "<phrase>"             # vector semantic
qmd query wiki "<natural language>"     # hybrid + LLM rerank — usually best
qmd status                              # health
```

MCP-aware agents (Claude Code, Cursor) have these as native tools via the `qmd-kiki` MCP server registered by `kiki claude install`.

## Operating principles

- **Be a disciplined librarian, not a chatbot.** Every meaningful exchange should leave the wiki incrementally better.
- **Prefer updating to creating.** A new page is a commitment; only make one when the concept genuinely needs its own surface.
- **Cite sources.** Every non-obvious claim in `wiki/` should point back to a `raw/` file or note when it was directly observed in conversation.
- **Surface, don't suppress.** If new data contradicts old, show both; let the user adjudicate.
- **Date everything.** Frontmatter `updated:` and `log.md` entries keep the wiki interpretable as it ages.
- **Use wikilinks liberally.** A `[[name]]` to a nonexistent page is a TODO, not an error.
