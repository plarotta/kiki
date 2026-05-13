#!/usr/bin/env bats
# tests/test_kiki.bats — smoke tests for the kiki CLI.
#
# Run from the repo root:    bats tests/
# Skips the subcommands that shell out to claude/qmd (covered by mocks below
# where feasible). The watcher and Claude/MCP install paths are covered by
# integration tests outside this file.

setup() {
  REPO="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  export KIKI_PREFIX="$REPO"
  export KIKI_HOME="$(mktemp -d)"
  export KIKI="$REPO/bin/kiki"
}

teardown() {
  rm -rf "$KIKI_HOME"
}

# ──────────────────────────────────────────────────────────────────────────────
# version / where / help
# ──────────────────────────────────────────────────────────────────────────────

@test "kiki version prints semver" {
  run "$KIKI" version
  [ "$status" -eq 0 ]
  [[ "$output" =~ ^kiki\ [0-9]+\.[0-9]+\.[0-9]+ ]]
}

@test "kiki where prints KIKI_HOME" {
  run "$KIKI" where
  [ "$status" -eq 0 ]
  [ "$output" = "$KIKI_HOME" ]
}

@test "kiki help mentions all subcommands" {
  run "$KIKI" help
  [ "$status" -eq 0 ]
  for sub in init capture ingest lint query watch claude doctor where version; do
    [[ "$output" == *"$sub"* ]] || { echo "missing: $sub"; return 1; }
  done
}

@test "kiki with no args shows help" {
  run "$KIKI"
  [ "$status" -eq 0 ]
  [[ "$output" == *"usage: kiki"* ]]
}

@test "kiki unknown-subcommand exits non-zero" {
  run "$KIKI" frobnicate
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown subcommand"* ]]
}

# ──────────────────────────────────────────────────────────────────────────────
# capture — happy path
# ──────────────────────────────────────────────────────────────────────────────

bootstrap_home() {
  mkdir -p "$KIKI_HOME/raw/notes" "$KIKI_HOME/raw/transcripts" "$KIKI_HOME/wiki"
  printf 'schema stub\n' > "$KIKI_HOME/CLAUDE.md"
}

@test "capture writes a note with frontmatter, signal, content" {
  bootstrap_home
  run bash -c "echo 'body line one' | '$KIKI' capture --type note --topic 'my topic' --signal 'why this matters'"
  [ "$status" -eq 0 ]
  out_path="$output"
  [ -f "$out_path" ]
  body="$(cat "$out_path")"
  [[ "$body" == *"type: note"* ]]
  [[ "$body" == *"topic: \"my topic\""* ]]
  [[ "$body" == *"ingested: false"* ]]
  [[ "$body" == *"## Signal"* ]]
  [[ "$body" == *"why this matters"* ]]
  [[ "$body" == *"## Content"* ]]
  [[ "$body" == *"body line one"* ]]
}

@test "capture writes a transcript with default participants" {
  bootstrap_home
  run bash -c "echo 'turn 1' | '$KIKI' capture --type transcript --topic 'session'"
  [ "$status" -eq 0 ]
  body="$(cat "$output")"
  [[ "$body" == *"type: transcript"* ]]
  [[ "$body" == *"participants: [user]"* ]]
}

@test "capture filename has YYYY-MM-DD prefix" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type note --topic 'whatever'"
  [ "$status" -eq 0 ]
  fname="$(basename "$output")"
  today="$(date +%Y-%m-%d)"
  [[ "$fname" == "${today}-"* ]]
}

@test "capture disambiguates colliding slugs" {
  bootstrap_home
  run bash -c "echo a | '$KIKI' capture --type note --topic 'collide'"
  [ "$status" -eq 0 ]
  first="$output"
  run bash -c "echo b | '$KIKI' capture --type note --topic 'collide'"
  [ "$status" -eq 0 ]
  second="$output"
  [ "$first" != "$second" ]
  [[ "$second" == *-2.md ]]
}

@test "capture slugifies topic" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type note --topic 'Tabs vs. Spaces?!'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"tabs-vs-spaces.md" ]]
}

@test "capture handles tags as a yaml list" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type note --topic t --tags 'a,b , c'"
  [ "$status" -eq 0 ]
  body="$(cat "$output")"
  [[ "$body" == *"tags: [a, b, c]"* ]]
}

@test "capture leaves no .tmp file behind" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type note --topic atomic"
  [ "$status" -eq 0 ]
  tmpfiles="$(find "$KIKI_HOME/raw" -name '*.tmp*')"
  [ -z "$tmpfiles" ]
}

# ──────────────────────────────────────────────────────────────────────────────
# capture — error paths
# ──────────────────────────────────────────────────────────────────────────────

@test "capture without --type fails" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --topic foo"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--type is required"* ]]
}

@test "capture without --topic fails" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type note"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--topic is required"* ]]
}

@test "capture with invalid --type fails" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type weirdness --topic foo"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--type must be"* ]]
}

@test "capture with invalid --confidence fails" {
  bootstrap_home
  run bash -c "echo body | '$KIKI' capture --type note --topic foo --confidence absolute"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--confidence must be"* ]]
}

@test "capture before init fails with helpful message" {
  # KIKI_HOME exists (mktemp -d) but CLAUDE.md is missing → require_home fails
  run bash -c "echo body | '$KIKI' capture --type note --topic foo"
  [ "$status" -ne 0 ]
  [[ "$output" == *"not initialized"* || "$output" == *"does not exist"* ]]
}

# ──────────────────────────────────────────────────────────────────────────────
# doctor exits non-zero when home isn't initialized
# ──────────────────────────────────────────────────────────────────────────────

@test "doctor exits non-zero on incomplete home" {
  rm -rf "$KIKI_HOME"   # no home at all
  run "$KIKI" doctor
  [ "$status" -ne 0 ]
  [[ "$output" == *"FAIL"* ]]
}

# ──────────────────────────────────────────────────────────────────────────────
# init — end-to-end scaffolding (regression test for the v0.1.2 silent-abort)
# ──────────────────────────────────────────────────────────────────────────────

@test "watch status reports loaded under set -o pipefail (SIGPIPE regression)" {
  # Reproduces the pre-0.1.4 bug: `launchctl list | grep -q LABEL` returned
  # 141 under pipefail because grep -q's early exit SIGPIPE'd launchctl,
  # falsely reporting "not loaded" even when the agent was present.
  local stub="$BATS_TEST_TMPDIR/stub"
  mkdir -p "$stub"
  cat > "$stub/launchctl" <<'SH'
#!/usr/bin/env bash
# Stub: print a launchctl-list-shaped table that contains the kiki watcher,
# padded with extra lines so the SIGPIPE race window is wider.
if [[ "$1" == "list" ]]; then
  printf 'PID\tStatus\tLabel\n'
  for i in $(seq 1 200); do printf -- '-\t0\tcom.apple.fake.%d\n' "$i"; done
  printf -- '-\t127\tcom.kiki.watcher\n'
  for i in $(seq 1 200); do printf -- '-\t0\tcom.apple.more.%d\n' "$i"; done
fi
SH
  chmod +x "$stub/launchctl"
  PATH="$stub:$PATH" run "$KIKI" watch status
  [ "$status" -eq 0 ]
  [[ "$output" == *"com.kiki.watcher: loaded"* ]]
  [[ "$output" != *"not loaded"* ]]
}

@test "init scaffolds and runs to completion (qmd present)" {
  command -v qmd >/dev/null 2>&1 || skip "qmd not installed"
  rm -rf "$KIKI_HOME"

  # Save/restore user's wiki collection so the test is hermetic w.r.t. qmd state.
  local saved_path=""
  saved_path="$(qmd collection show wiki 2>/dev/null | awk '/^  Path:/ {print $2; exit}')" || true
  qmd collection remove wiki >/dev/null 2>&1 || true

  # Decline embed, watcher, and claude-skill prompts (3 confirms).
  run bash -c "printf 'n\nn\nn\n' | '$KIKI' init"
  local rc=$status

  # Restore qmd state before asserting (so a test failure doesn't leak state).
  qmd collection remove wiki >/dev/null 2>&1 || true
  if [[ -n "$saved_path" ]]; then
    qmd collection add "$saved_path" >/dev/null 2>&1 || true
  fi

  [ "$rc" -eq 0 ]
  [ -d "$KIKI_HOME/raw/notes" ]
  [ -d "$KIKI_HOME/raw/transcripts" ]
  [ -d "$KIKI_HOME/wiki" ]
  [ -f "$KIKI_HOME/CLAUDE.md" ]
  [[ "$output" == *"kiki initialized"* ]]
}
