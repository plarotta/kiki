# Changelog

All notable changes to kiki are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
