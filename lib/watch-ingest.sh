#!/usr/bin/env bash
# lib/watch-ingest.sh — invoked by launchd when something changes in
# $KIKI_HOME/raw/{notes,transcripts}.
#
# Diffs the dirs against $KIKI_HOME/.state/processed.txt, invokes `claude -p`
# headlessly to ingest each new file (following CLAUDE.md), then runs one lint
# pass. Idempotent; protected by a flock against overlapping runs.

set -euo pipefail

KIKI_HOME="${KIKI_HOME:-$HOME/.kiki}"
STATE_DIR="$KIKI_HOME/.state"
MANIFEST="$STATE_DIR/processed.txt"
LOGFILE="$STATE_DIR/watcher.log"
LOCKDIR="$STATE_DIR/watcher.lock.d"

# launchd doesn't load .zshrc — give claude/qmd a sane PATH.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$STATE_DIR"
touch "$MANIFEST"
cd "$KIKI_HOME"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOGFILE"
}

# Single-flight lock. mkdir(2) is atomic on POSIX, so we use a directory as a
# portable mutex (macOS doesn't ship flock(1)). A run older than 30 minutes is
# assumed stale (prior hard crash) and reclaimed.
if [[ -d "$LOCKDIR" ]] && find "$LOCKDIR" -maxdepth 0 -mmin +30 2>/dev/null | grep -q .; then
  log "reclaiming stale lock (>30min old)"
  rmdir "$LOCKDIR" 2>/dev/null || true
fi
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  log "another watcher run is in progress; exiting"
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT

sleep 3  # debounce: let files finish landing

mapfile -t ALL < <(find raw/notes raw/transcripts -type f -name '*.md' 2>/dev/null | sort)

NEW=()
for f in "${ALL[@]}"; do
  rel="${f#"$KIKI_HOME/"}"
  if ! grep -Fxq "$rel" "$MANIFEST" 2>/dev/null; then
    NEW+=("$rel")
  fi
done

if [[ ${#NEW[@]} -eq 0 ]]; then
  log "no new files; exiting"
  exit 0
fi

log "found ${#NEW[@]} new file(s): ${NEW[*]}"

if ! command -v claude >/dev/null 2>&1; then
  log "ERROR: 'claude' not on PATH ($PATH); aborting"
  exit 1
fi

for rel in "${NEW[@]}"; do
  log "ingesting: $rel"
  prompt="Ingest the file \`$rel\` following the ingest workflow in CLAUDE.md. \
Steps: (1) read CLAUDE.md first if you haven't already, (2) read \`$rel\` end-to-end, \
(3) update relevant wiki pages (persona, preferences, style, feedback, projects, entities, concepts) \
preferring updates over new pages, (4) flag any contradictions with existing claims, \
(5) update wiki/index.md, (6) append a log entry to wiki/log.md using the format \
'## [YYYY-MM-DD] ingest | <title>', (7) run 'qmd update'. \
Finally, set 'ingested: true' in the source file's frontmatter. Be terse in your final report."
  if claude -p "$prompt" --dangerously-skip-permissions >> "$LOGFILE" 2>&1; then
    printf '%s\n' "$rel" >> "$MANIFEST"
    log "ingested ok: $rel"
  else
    rc=$?
    log "ingest FAILED for $rel (exit $rc) — not adding to manifest, will retry next run"
  fi
done

log "running lint pass"
lint_prompt="Run the lint workflow defined in CLAUDE.md against the wiki. \
Look for contradictions, stale claims, orphan pages, dangling [[wikilinks]], concept inflation, and index drift. \
Fix safe issues (dangling links, missing index entries) yourself. \
For anything that requires judgment (deleting orphans, resolving contradictions), report and skip. \
Append a log entry '## [YYYY-MM-DD] lint | <summary>'. Be terse."
if claude -p "$lint_prompt" --dangerously-skip-permissions >> "$LOGFILE" 2>&1; then
  log "lint ok"
else
  rc=$?
  log "lint FAILED (exit $rc)"
fi

log "watcher run complete"
