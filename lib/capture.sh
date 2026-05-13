#!/usr/bin/env bash
# lib/capture.sh — write a note or transcript into $KIKI_HOME/raw/ with the kiki schema.
#
# Stand-alone usable; also invoked by `kiki capture`. Body read from STDIN.

set -euo pipefail

KIKI_HOME="${KIKI_HOME:-$HOME/.kiki}"

usage() {
  cat <<'EOF'
Usage: capture --type (note|transcript) --topic "..." [options] < body

Required:
  --type TYPE             "note" or "transcript"
  --topic STR             short noun phrase; becomes part of the filename

Optional:
  --tags "a,b,c"          comma-separated tags
  --source STR            how this was captured (e.g. "claude-code-session")
  --captured-by STR       agent or user name
  --confidence LEVEL      low | medium | high
  --related "[[a]],[[b]]" links to related wiki pages
  --participants "u,c"    transcripts only; comma-separated participants
  --signal STR            1-2 line hint telling the ingestor what this is for
  -h, --help              show this help

Output: prints the absolute path of the file written, one line on stdout.

Environment:
  KIKI_HOME               wiki root (default: ~/.kiki); must exist
EOF
}

# ──────────────────────────────────────────────────────────────────────────────
# arg parsing
# ──────────────────────────────────────────────────────────────────────────────
TYPE=""
TOPIC=""
TAGS=""
SOURCE=""
CAPTURED_BY=""
CONFIDENCE=""
RELATED=""
PARTICIPANTS=""
SIGNAL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)         TYPE="${2:?--type requires a value}";          shift 2 ;;
    --topic)        TOPIC="${2:?--topic requires a value}";         shift 2 ;;
    --tags)         TAGS="${2:-}";          shift 2 ;;
    --source)       SOURCE="${2:-}";        shift 2 ;;
    --captured-by)  CAPTURED_BY="${2:-}";   shift 2 ;;
    --confidence)   CONFIDENCE="${2:-}";    shift 2 ;;
    --related)      RELATED="${2:-}";       shift 2 ;;
    --participants) PARTICIPANTS="${2:-}";  shift 2 ;;
    --signal)       SIGNAL="${2:-}";        shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *) printf 'capture: unknown arg: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -z "$TYPE"  ]] && { echo "capture: --type is required (note|transcript)" >&2; exit 2; }
[[ -z "$TOPIC" ]] && { echo "capture: --topic is required" >&2; exit 2; }

case "$TYPE" in
  note)       SUBDIR="raw/notes" ;;
  transcript) SUBDIR="raw/transcripts" ;;
  *) echo "capture: --type must be 'note' or 'transcript' (got: $TYPE)" >&2; exit 2 ;;
esac

case "${CONFIDENCE:-}" in
  ""|low|medium|high) ;;
  *) echo "capture: --confidence must be low|medium|high (got: $CONFIDENCE)" >&2; exit 2 ;;
esac

if [[ ! -d "$KIKI_HOME" ]]; then
  echo "capture: \$KIKI_HOME ($KIKI_HOME) does not exist — run 'kiki init' first" >&2
  exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | LC_ALL=C sed -e 's/[^a-z0-9]\{1,\}/-/g' -e 's/^-//' -e 's/-$//' \
    | cut -c1-60
}

yaml_list() {
  local raw="${1:-}"
  [[ -z "$raw" ]] && { printf '[]'; return; }
  local out="" item
  local IFS=','
  for item in $raw; do
    item="${item#"${item%%[![:space:]]*}"}"
    item="${item%"${item##*[![:space:]]}"}"
    [[ -z "$item" ]] && continue
    if [[ -z "$out" ]]; then out="$item"; else out="$out, $item"; fi
  done
  printf '[%s]' "$out"
}

yaml_str() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '"%s"' "$s"
}

# ──────────────────────────────────────────────────────────────────────────────
# resolve output path (disambiguate if same slug already exists today)
# ──────────────────────────────────────────────────────────────────────────────
SLUG="$(slugify "$TOPIC")"
[[ -z "$SLUG" ]] && SLUG="entry"

DATE_ISO="$(date +%Y-%m-%dT%H:%M:%S%z)"
DATE_DAY="$(date +%Y-%m-%d)"

mkdir -p "$KIKI_HOME/$SUBDIR"

BASE="$KIKI_HOME/$SUBDIR/${DATE_DAY}-${SLUG}"
OUT="${BASE}.md"
n=2
while [[ -e "$OUT" ]]; do
  OUT="${BASE}-${n}.md"
  n=$((n + 1))
done

TAGS_YAML="$(yaml_list "$TAGS")"
[[ "$TYPE" == "transcript" && -z "$PARTICIPANTS" ]] && PARTICIPANTS="user"
PARTS_YAML="$(yaml_list "$PARTICIPANTS")"

# ──────────────────────────────────────────────────────────────────────────────
# atomic write — write to a sibling tmpfile, then rename. Prevents the watcher
# from seeing a partially-written file (its WatchPaths fires on inode events).
# ──────────────────────────────────────────────────────────────────────────────
TMP="$(mktemp "${OUT}.XXXXXX.tmp")"
trap 'rm -f "$TMP"' EXIT

{
  echo "---"
  echo "type: $TYPE"
  echo "created: $DATE_ISO"
  echo "topic: $(yaml_str "$TOPIC")"
  [[ -n "$SOURCE"      ]] && echo "source: $(yaml_str "$SOURCE")"
  [[ -n "$CAPTURED_BY" ]] && echo "captured_by: $(yaml_str "$CAPTURED_BY")"
  if [[ "$TYPE" == "transcript" ]]; then
    echo "participants: $PARTS_YAML"
  fi
  echo "tags: $TAGS_YAML"
  [[ -n "$RELATED"    ]] && echo "related: $(yaml_str "$RELATED")"
  [[ -n "$CONFIDENCE" ]] && echo "confidence: $CONFIDENCE"
  echo "ingested: false"
  echo "---"
  echo
  echo "# $TOPIC"
  echo
  if [[ -n "$SIGNAL" ]]; then
    echo "## Signal"
    echo
    echo "$SIGNAL"
    echo
  fi
  echo "## Content"
  echo
  cat
  echo
} > "$TMP"

mv "$TMP" "$OUT"
trap - EXIT

printf '%s\n' "$OUT"
