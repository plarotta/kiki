# Changelog

All notable changes to kiki are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-05-14

### Added
- **Multi-provider ingest backends.** `kiki ingest` can now route to
  Anthropic's API, OpenAI, Google Gemini, or a local Ollama instance
  in addition to the default `claude -p` Claude Code path. Selection
  via `KIKI_PROVIDER=anthropic|openai|gemini|ollama` (env), or in
  `$KIKI_HOME/config.toml`:

      [ingest]
      provider = "openai"
      model = "gpt-5"

  API keys come from the standard env vars (`ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `GEMINI_API_KEY`); Ollama uses `OLLAMA_BASE_URL`
  (default `http://localhost:11434`). Env always overrides config.
- `lib/providers.py` — stdlib-only HTTP adapters for each provider.
  No new pip dependencies.
- `lib/ingest.py` — single-shot orchestrator: collects current wiki
  state + the raw note, asks the provider for a structured JSON edit
  plan (constrained via tool/json-schema/responseSchema/format=json
  per provider), applies the edits to wiki/, appends a log entry,
  flips `ingested: true`, and runs `qmd update`.
- New `KIKI_MODEL` env var to override the model per-provider.
- `kiki ingest --help` documents the new env vars.

### Notes
- The default behavior is unchanged: with no `KIKI_PROVIDER` and no
  `[ingest] provider` in config, `kiki ingest` still shells to
  `claude -p` (the agentic path).
- The non-claude providers use a single API call (no tool-use loop)
  with the entire wiki sent in the prompt. For kiki's small
  fixed-page schema this is fine; bigger wikis may exceed context.
- Local Ollama models need to be capable enough to follow a JSON
  schema reliably. Small models (e.g. gemma3:4b) tend to return
  no-op plans. Use a 30B+ model for best results.
- `kiki lint` and the launchd watcher still use the `claude -p`
  path. Migrating those is the next step.

## [0.1.5] — 2026-05-13

### Added
- `kiki ingest` and `kiki lint` now stream progress in real time
  instead of printing a single final blob after a long silent wait.
  As `claude -p` works through the ingest, you see each tool call
  ("→ Read wiki/index.md", "→ Edit wiki/log.md", "→ Bash: qmd update")
  and assistant text appears as it's generated, capped with a
  duration/cost line. Driven by a small `lib/stream-claude.py` that
  parses `--output-format stream-json --include-partial-messages`.
- `KIKI_VERBOSE=1` (or `-v`) now also affects ingest/lint: tool
  inputs are shown un-truncated (paths, full bash commands).

### Fixed
- `info "ingesting $rel…"` triggered `unbound variable: rel<garbled>`
  under `set -u` because bash consumed the leading bytes of the `…`
  multi-byte UTF-8 char as part of the variable name. Braces fix it.

## [0.1.4] — 2026-05-13

### Fixed
- **`kiki watch status` falsely reported "not loaded" even when the
  agent was loaded.** Root cause: under `set -o pipefail`,
  `launchctl list | grep -q LABEL` returns 141 — `grep -q` exits at
  first match, SIGPIPE'ing `launchctl`, and pipefail propagates that
  to the pipeline. The `if` block then took the else branch.
  `kiki doctor` worked only because it wrapped its check in
  `sh -c "..."` (a subshell without `pipefail` inherited), so the two
  commands genuinely reported different states for the same agent.
  Replaced the pipeline with pure-bash substring matching in two new
  helpers, `launchd_agent_loaded()` and `qmd_collection_exists()`,
  used everywhere the old pattern lived (watch status, uninstall,
  doctor).

### Added
- bats test `watch status reports loaded under set -o pipefail
  (SIGPIPE regression)` — stubs `launchctl` on PATH with a long
  output that widens the SIGPIPE race window.

## [0.1.3] — 2026-05-13

### Fixed
- **`kiki init` aborted silently right after "registering qmd collection
  'wiki'".** Regression in 0.1.2: a `local current_path` declaration
  followed by a separate pipeline assignment interacted with
  `set -euo pipefail`. When `qmd collection show wiki` exited non-zero
  (the normal case on first run — no collection yet), the pipeline's
  non-zero exit propagated to the assignment, which `set -e` treated as
  a fatal error. No watcher, no skill, no embed prompt. Added `|| true`
  to the assignment.

### Added
- bats test `init scaffolds and runs to completion (qmd present)` —
  end-to-end smoke test that exercises `kiki init` against a fresh
  `$KIKI_HOME` so this regression can't ship silently again.

## [0.1.2] — 2026-05-13

### Fixed
- **Watcher was broken on macOS.** `lib/watch-ingest.sh` used `flock(1)`,
  which isn't shipped with macOS. Every WatchPaths fire exited via the
  error path, so no captured notes were ever ingested. Replaced with a
  portable `mkdir(2)`-based lock with stale-lock (>30min) reclamation.
- **qmd 'wiki' collection registered against the wrong path.** `qmd
  collection add wiki <path>` ignores the second positional arg and uses
  `CWD/<name>`. We now call `qmd collection add <absolute-path>` (qmd
  derives the name from the basename) and detect path drift on every
  `kiki init`, re-registering against `$KIKI_HOME/wiki` if needed.

### Added
- `kiki uninstall [--purge]` — remove the launchd watcher, Claude skill,
  MCP entries, and qmd `wiki` collection in one shot. `--purge` also
  removes `$KIKI_HOME` (with confirmation). `brew uninstall` remains the
  user's call.
- `-v` / `--verbose` global flag (and `KIKI_VERBOSE=1`) — surfaces
  output from qmd/claude calls that are normally swallowed; prints
  debug lines for major steps.
- Subcommands that need `$KIKI_HOME` now auto-offer to run `kiki init`
  on interactive TTYs when the home is missing.
- Light ANSI colors for `kiki doctor` (green ok, red FAIL, cyan
  headings) and `kiki: ...` error prefixes. Respects `NO_COLOR`.

### Changed
- `-v` no longer aliases `version`; use `-V` / `--version` / `version`.

## [0.1.1] — 2026-05-13

### Changed
- `kiki capture`: when stdin is a TTY, print a hint to stderr explaining that
  the body is being read from stdin (Ctrl+D to finish). Previously the command
  appeared to hang silently.
- `kiki init`: bracket the `qmd embed` call with progress messages so users
  know the ~330MB embedding-model download is in progress on first run.

## [0.1.0] — 2026-05-12

Initial release.

### Added
- `kiki` CLI with subcommands: `init`, `capture`, `ingest`, `lint`, `query`,
  `watch`, `claude`, `doctor`, `where`, `version`.
- `lib/capture.sh` — schema-aware writer for `$KIKI_HOME/raw/{notes,transcripts}`.
- `lib/watch-ingest.sh` — launchd-invoked watcher that runs headless ingest +
  lint via `claude -p` for each new raw file.
- `mcp/kiki-mcp.py` — MCP server exposing `capture` and `where` tools for
  MCP-aware agents (Claude Code, Cursor).
- `templates/` — `CLAUDE.md` schema, seed wiki pages, and the `kiki-capture`
  skill, copied to `$KIKI_HOME` and `~/.claude/skills/` on `kiki init` /
  `kiki claude install`.
- `Formula/kiki.rb` — Homebrew formula (macOS).
- `bats` smoke tests, `shellcheck` lint, GitHub Actions CI.
