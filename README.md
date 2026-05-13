# kiki

[![ci](https://github.com/plarotta/kiki/actions/workflows/ci.yml/badge.svg)](https://github.com/plarotta/kiki/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![brew tap](https://img.shields.io/badge/brew%20tap-plarotta%2Fkiki-orange)](https://github.com/plarotta/homebrew-tap)

A persistent memory wiki for your LLM coding assistant.

You drop notes and transcripts into `~/.kiki/raw/`; a background watcher reads
them and incrementally maintains a structured wiki (persona, preferences,
style, feedback, projects, entities, concepts) about you. Your assistant then
reads the wiki to adapt — across sessions, across projects, across agents.

> Status: **v0.1.0 — alpha, macOS only.** See [`desc.md`](desc.md) for the
> underlying pattern.

## TL;DR

```bash
brew tap plarotta/kiki
brew install kiki
kiki init        # scaffolds ~/.kiki, offers to install watcher + Claude skill
kiki doctor      # green check across the board
```

From then on, your assistant captures into the wiki via `kiki capture`, the
launchd watcher auto-ingests, and `kiki query "..."` (or the qmd MCP tool)
answers questions over it.

---

## How it works

```text
agent ──`kiki capture`──▶ ~/.kiki/raw/notes/foo.md
                              │
                       (launchd WatchPaths)
                              │
                              ▼
                       claude -p "ingest" + "lint"
                              │
                              ▼
                       ~/.kiki/wiki/* updated
```

Three layers:

- **`raw/`** — immutable source notes/transcripts deposited by `kiki capture`.
- **`wiki/`** — assistant-maintained structured markdown. Plain `.md` files,
  Obsidian-style `[[wikilinks]]`, YAML frontmatter.
- **`.state/`** — runtime bookkeeping (processed-manifest, lockfile, watcher log).

The assistant reads `CLAUDE.md` (the schema, copied into `~/.kiki/` on init)
to know how to maintain the wiki.

---

## Daily use

Most of the time, *you* don't run kiki — your agent does.

### Capture

```bash
echo "User prefers tabs over spaces." | kiki capture \
  --type note \
  --topic "indentation preference" \
  --tags "preferences,coding" \
  --signal "concrete preference; file under preferences.md"
```

The watcher fires within ~10s, runs `claude -p` to ingest the note into the
structured wiki, runs a lint pass, and updates the qmd index. Watch it happen:

```bash
kiki watch logs
```

### Query

```bash
kiki query "what does the user think about testing?"
```

MCP-aware agents (Claude Code, Cursor) get this as a native tool — no shelling
out — via the `qmd-kiki` MCP server registered by `kiki claude install`.

### Browse

The wiki is plain markdown. Open `~/.kiki/wiki/` in your editor of choice
(Obsidian, VS Code, anything) when you want to read it.

---

## Commands

| Command | Behavior |
|---|---|
| `kiki init` | Scaffold `~/.kiki/`; register qmd collection; offer to install watcher + Claude skill. |
| `kiki capture --type ... --topic "..."` | Write a note/transcript into `raw/`. Body via stdin. |
| `kiki ingest <file>` | Manual one-shot ingest (the watcher runs this automatically). |
| `kiki lint` | Manual one-shot lint. |
| `kiki query "..."` | Wraps `qmd query wiki "..."`. |
| `kiki watch (install\|uninstall\|status\|logs)` | Manage the launchd agent. |
| `kiki claude (install\|uninstall)` | Install/remove the Claude Code skill + MCP server entries. |
| `kiki doctor` | Verify install, dependencies, watcher, skill, MCP. |
| `kiki where` | Print `$KIKI_HOME`. |
| `kiki version` | Print version. |

---

## Configuration

- **`$KIKI_HOME`** — wiki location. Default: `~/.kiki`. Override if you want
  the wiki to live somewhere else (e.g. inside an iCloud/Dropbox folder).
- **`$KIKI_PREFIX`** — where `kiki` looks for its `lib/` and `templates/`.
  Auto-detected via `brew --prefix` or the script's parent dir. Only set if
  you're running from a non-standard location.
- **`$KIKI_YES=1`** — non-interactive mode (`kiki init` skips confirm prompts).

No config file. The env vars cover everything.

---

## Agent surfaces

Three integration channels, all installed by `kiki claude install`:

1. **Claude Code skill** at `~/.claude/skills/kiki-capture/SKILL.md` —
   auto-discovered in any Claude session regardless of cwd. Tells the agent
   when and how to capture.
2. **MCP tools** registered in `~/.claude.json`:
   - `kiki` server — `capture(...)`, `where()` tools.
   - `qmd-kiki` server — qmd's built-in search/vsearch/query over the `wiki`
     collection.
3. **Plain CLI** (`kiki capture`, `kiki query`) — any agent that can shell out
   uses this: Codex, Cursor, raw scripts, the human.

---

## External tools

kiki integrates with several tools it does **not** install for you, so you can
use the versions you already have:

| Tool | Used for | How to get it |
|---|---|---|
| [Claude Code](https://github.com/anthropics/claude-code) | Headless ingest/lint via `claude -p` | Install separately. |
| [qmd](https://github.com/tobi/qmd) | Hybrid BM25+vector+rerank search over the wiki | `kiki init` offers `npm install -g @tobilu/qmd`. |
| [`mcp`](https://pypi.org/project/mcp/) (PyPI) | Python MCP SDK used by `kiki-mcp` | `pip3 install --user mcp` |

`kiki doctor` flags any that are missing.

---

## How the watcher works

`kiki watch install` writes a launchd `LaunchAgent` plist that uses `WatchPaths`
to watch `~/.kiki/raw/{notes,transcripts}`. On any change (10s throttle, 3s
internal debounce), it runs `lib/watch-ingest.sh`:

1. Diffs the dirs against `~/.kiki/.state/processed.txt`.
2. For each new file, invokes `claude -p` headlessly with the ingest prompt
   from `CLAUDE.md`.
3. After all files, runs `claude -p` once more for a lint pass.
4. Appends processed paths to the manifest.

A `flock` lockfile prevents overlapping runs. Output goes to
`~/.kiki/.state/watcher.log` — `kiki watch logs` tails it.

The headless `claude -p` uses `--dangerously-skip-permissions` because launchd
can't answer interactive prompts. The watcher's writes are confined to
`$KIKI_HOME`.

---

## Uninstall

```bash
kiki watch uninstall
kiki claude uninstall
brew uninstall kiki
```

Your wiki data at `~/.kiki/` is **never** touched. Remove it yourself when
you're sure: `rm -rf ~/.kiki`.

---

## Troubleshooting

`kiki doctor` is the first stop. Common issues:

- **`claude` not on PATH.** Install [Claude Code](https://github.com/anthropics/claude-code).
- **`qmd` missing.** Run `kiki init` again, or `npm install -g @tobilu/qmd`.
- **MCP server fails to import `mcp`.** `pip3 install --user mcp`.
- **Watcher doesn't fire.** `kiki watch status`. The plist's `WatchPaths` must
  reference existing directories — `kiki init` ensures this; if you blew away
  `raw/notes/`, re-create it.
- **Embeddings download is slow.** First run of `qmd embed` pulls a ~330MB GGUF
  model. Subsequent runs are fast.

---

## Development

```bash
git clone https://github.com/plarotta/kiki
cd kiki

# Run the CLI directly without installing
KIKI_PREFIX=$PWD ./bin/kiki version

# All checks (shellcheck + bats + brew style + brew audit)
make check
```

See [`CHANGELOG.md`](CHANGELOG.md) for release notes.

## Publishing checklist

For maintainers cutting a new release. kiki uses the standard Homebrew
two-repo pattern: source code here, formula mirrored to a tap.

1. **Bump the version** in `bin/kiki` (`VERSION="..."`), `Formula/kiki.rb`
   (`url` and any `version` reference), and `CHANGELOG.md`.
2. **`make check`** — must pass clean locally.
3. **Tag and push:**

   ```bash
   git tag -a v0.1.0 -m "v0.1.0"
   git push --tags
   ```

4. **Compute the tarball sha256** and patch the formula:

   ```bash
   curl -sL "https://github.com/plarotta/kiki/archive/refs/tags/v0.1.0.tar.gz" | shasum -a 256
   # paste into Formula/kiki.rb sha256 line
   ```

5. **Mirror `Formula/kiki.rb` to the tap** at `github.com/plarotta/homebrew-kiki`:

   ```bash
   # in a checkout of plarotta/homebrew-kiki:
   cp ~/src/kiki/Formula/kiki.rb Formula/
   git commit -m "kiki 0.1.0" && git push
   ```

6. **Verify the install path** end-to-end:

   ```bash
   brew untap plarotta/kiki 2>/dev/null || true
   brew tap plarotta/kiki
   brew install kiki
   kiki version && kiki doctor
   ```

---

## License

MIT — see [`LICENSE`](LICENSE).
