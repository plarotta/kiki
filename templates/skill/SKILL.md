---
name: kiki-capture
description: Drop a note or transcript into the user's kiki memory wiki ($KIKI_HOME, default ~/.kiki). Use whenever the user reveals a preference, style choice, correction, validated approach, fact about themselves, or shares a conversation worth preserving. The launchd watcher (if installed) auto-ingests the file into the structured wiki.
---

# kiki-capture

A skill for writing into `$KIKI_HOME/raw/` (the raw layer of the user's persistent assistant-memory wiki) with a consistent, ingest-friendly schema. Once a file lands, the launchd watcher fires `lib/watch-ingest.sh`, which runs a headless `claude -p` to ingest the file into the structured wiki and run a lint pass.

## When to invoke this skill

Invoke whenever something happens that is worth preserving across sessions:

- The user states a **preference** — coding style, naming, tooling, workflow, communication style.
- The user **corrects** the assistant's behavior ("don't do X", "stop summarizing", "you got this wrong").
- The user **validates** a non-obvious approach ("yes, exactly", "perfect, keep doing that").
- The user reveals a **fact about themselves** — role, expertise, projects, constraints, goals.
- A coding/chat session produced a **non-obvious insight** that an ingest could mine.
- The user explicitly says "save this", "remember this", "capture this".

## When NOT to invoke

- Ephemeral state of the current task.
- Information already in `$KIKI_HOME/CLAUDE.md` or already obvious from reading the code.
- Trivia with no relevance to how an assistant should behave.
- Anything sensitive the user hasn't asked to be persisted.

## How to invoke

Call `kiki capture` (it's on `PATH` after `brew install kiki`). Body via stdin.

```bash
echo "<body content>" | kiki capture \
  --type note|transcript \
  --topic "<short noun phrase>" \
  [--tags "tag1,tag2"] \
  [--source "<how this was captured>"] \
  [--captured-by "<agent or user>"] \
  [--confidence low|medium|high] \
  [--related "[[page]],[[other-page]]"] \
  [--participants "user,claude"]   # transcripts only \
  [--signal "<1-2 lines: why this is worth keeping; where it should be filed>"]
```

The command prints the absolute path of the file written.

## Picking `--type`

| Type         | Use for                                                                  |
|--------------|--------------------------------------------------------------------------|
| `note`       | A discrete observation, fact, preference, or insight (≤~30 lines).       |
| `transcript` | A captured conversation or session excerpt; longer, multi-turn material. |

If unsure, prefer `note`.

## The `--signal` flag is important

The `signal` is a 1–2 line hint that tells the ingestor what the entry is *for* — which wiki page(s) it should update, and what the headline claim is. Without it, the ingestor has to re-derive the point from the body, which is slower and lossier. Always write one.

Good signals:
- `"Concrete preference for testing tools; update preferences.md → Tools section."`
- `"Validated approach to PR splitting; add to feedback.md under 'Validated'."`
- `"Background fact about the user's role; update persona.md → Identity."`

Bad signals:
- `"Some thoughts."`
- (omitting it)

## Examples

### Captured correction

```bash
echo "User said: 'don't ever skip pre-commit hooks. We had a leak last quarter.'" \
  | kiki capture \
    --type note \
    --topic "no skipping pre-commit hooks" \
    --tags "feedback,git,security" \
    --source "claude-code-session" \
    --captured-by "claude" \
    --confidence high \
    --signal "Hard rule + reason. File under feedback.md → Corrections. Cross-link from preferences.md."
```

### Short session transcript

```bash
cat <<'EOF' | kiki capture \
  --type transcript \
  --topic "debugging react hydration error" \
  --tags "projects,react,debugging" \
  --participants "user,claude" \
  --source "claude-code-session" \
  --signal "Resolved hydration bug by inspecting Suspense boundaries; pattern worth filing in concepts/."
**User:** I'm getting a hydration mismatch on the dashboard route.
**Assistant:** ...
EOF
```

### Self-observation made mid-conversation

```bash
echo "User pushed back on suggesting a redux refactor; they prefer staying with context for small apps." \
  | kiki capture \
    --type note \
    --topic "redux vs context preference for small apps" \
    --tags "preferences,react,state-management" \
    --confidence medium \
    --signal "Architectural preference, scope = small apps. File under preferences.md → Coding."
```

## Schema reference

```yaml
---
type: note                       # or 'transcript'
created: 2026-05-12T14:30:00-0700
topic: "verbosity preference"
source: "claude-code-session"    # optional but recommended
captured_by: "claude"            # optional but recommended
participants: [user, claude]     # transcripts only
tags: [preferences, style]
related: "[[persona]],[[style]]" # optional
confidence: high                 # optional
ingested: false                  # flipped to true once the ingest workflow runs
---

# <topic>

## Signal

<1-2 lines: why this is worth keeping; where it should be filed>

## Content

<the body, from stdin>
```

## Operating rules

1. **One concept per file.** Two distinct observations → two files. The ingestor handles many small files better than one stuffed one.
2. **Date is automatic.** Filename gets a `YYYY-MM-DD-` prefix; don't include the date in `--topic`.
3. **Cite where you can.** If the observation came from a specific message, paste the relevant excerpt into Content rather than paraphrasing.
4. **Don't rewrite history.** If you got a fact wrong in a previous note, write a new note that corrects it — don't edit the old one. The ingest workflow will reconcile.
5. **Don't touch `wiki/` directly.** That layer is owned by the ingest workflow. Capture writes to `raw/` only.

## If `kiki` isn't installed

`command -v kiki` will fail. Tell the user: `brew install plarotta/tap/kiki && kiki init`.
