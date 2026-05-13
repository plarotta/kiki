# Changelog

All notable changes to kiki are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
