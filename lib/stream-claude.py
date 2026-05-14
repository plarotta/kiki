#!/usr/bin/env python3
"""
Render claude's stream-json events into incremental human-readable progress.

Reads NDJSON from stdin (output of `claude -p --output-format stream-json
--include-partial-messages --verbose`), emits:
  - tool_use markers on stderr   ("→ Read wiki/index.md")
  - assistant text deltas on stdout (streamed)
  - a duration/cost summary on stderr

With KIKI_VERBOSE=1, tool_use markers also include input details for tools
like Bash, Grep, Edit (their command/pattern). Otherwise they show only the
target file path or a brief hint.

Exit code mirrors claude's: non-zero if the result event reports is_error.
"""
import json
import os
import sys

VERBOSE = os.environ.get("KIKI_VERBOSE") == "1"


def tool_hint(name: str, inp: dict) -> str:
    if not isinstance(inp, dict):
        return ""
    # Prefer the most action-revealing field per tool.
    for key in ("file_path", "path", "pattern", "command", "url"):
        v = inp.get(key)
        if isinstance(v, str) and v:
            if VERBOSE or len(v) <= 60:
                return v
            return v[:57] + "..."
    return ""


def main() -> int:
    seen_text = False
    exit_code = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue

        t = ev.get("type")

        # Top-level assistant message: contains complete content blocks (with
        # full tool_use input). Use this as the authoritative tool announce.
        if t == "assistant":
            msg = ev.get("message", {})
            for block in msg.get("content", []) or []:
                if block.get("type") == "tool_use":
                    name = block.get("name", "?")
                    hint = tool_hint(name, block.get("input", {}))
                    if seen_text:
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        seen_text = False
                    if hint:
                        sys.stderr.write(f"  → {name}: {hint}\n")
                    else:
                        sys.stderr.write(f"  → {name}\n")
                    sys.stderr.flush()

        # Streamed text deltas: write inline as they arrive.
        elif t == "stream_event":
            evt = ev.get("event", {})
            if evt.get("type") == "content_block_delta":
                delta = evt.get("delta", {})
                if delta.get("type") == "text_delta":
                    sys.stdout.write(delta.get("text", ""))
                    sys.stdout.flush()
                    seen_text = True

        # Final result envelope.
        elif t == "result":
            if seen_text:
                sys.stdout.write("\n")
                sys.stdout.flush()
            if ev.get("is_error"):
                exit_code = 1
                err = ev.get("result") or "unknown error"
                sys.stderr.write(f"  ✗ claude error: {err}\n")
            else:
                ms = ev.get("duration_ms", 0) or 0
                cost = ev.get("total_cost_usd", 0) or 0
                sys.stderr.write(
                    f"  ✓ done in {ms / 1000:.1f}s — ${cost:.4f}\n"
                )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
