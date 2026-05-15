#!/usr/bin/env python3
"""
Multi-provider ingest orchestrator for kiki.

Usage: python3 lib/ingest.py <raw_file>

Loads `$KIKI_HOME/config.toml` (env vars override), collects the current
wiki state, asks the configured LLM provider to produce a structured
ingest plan, applies the plan's edits to wiki/, appends a log entry,
flips the source frontmatter to `ingested: true`, and runs `qmd update`.

Prints a streaming-style progress log to stderr; final summary on stdout.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Make sibling providers.py importable when this script is run by absolute path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import providers as P  # noqa: E402

try:
    import tomllib
except ImportError:
    sys.exit("kiki ingest: needs Python 3.11+ for tomllib; please upgrade")


VERBOSE = os.environ.get("KIKI_VERBOSE") == "1"


# ──────────────────────────────────────────────────────────────────────────────
# Schema returned by the model
# ──────────────────────────────────────────────────────────────────────────────

INGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One-line summary of what was done (or why nothing was done).",
        },
        "log_entry": {
            "type": "string",
            "description": "Markdown log line in the form: '## [YYYY-MM-DD] ingest | <title>\\n<one-or-two-sentence body>'. Empty string for no-op ingests.",
        },
        "page_edits": {
            "type": "array",
            "description": "Edits to apply to wiki pages. Empty array if no changes warranted.",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "string", "description": "Relative path within wiki/, e.g. 'preferences.md' or 'entities/qmd.md'."},
                    "operation": {"type": "string", "enum": ["create", "append", "replace", "edit"]},
                    "section": {"type": "string", "description": "Section heading for 'append' (the new content is appended under this heading; created if missing)."},
                    "content": {"type": "string", "description": "New content (for create/append/replace)."},
                    "edit_old": {"type": "string", "description": "For 'edit': exact existing text to find."},
                    "edit_new": {"type": "string", "description": "For 'edit': replacement text."},
                },
                "required": ["page", "operation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "log_entry", "page_edits"],
    "additionalProperties": False,
}


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

def load_config(kiki_home: Path) -> dict:
    cfg_path = kiki_home / "config.toml"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = tomllib.loads(cfg_path.read_text())
        except tomllib.TOMLDecodeError as e:
            sys.exit(f"kiki ingest: malformed {cfg_path}: {e}")

    ingest = cfg.get("ingest", {})
    provider = os.environ.get("KIKI_PROVIDER") or ingest.get("provider")
    model    = os.environ.get("KIKI_MODEL")    or ingest.get("model")

    if not provider:
        sys.exit("kiki ingest: no provider selected (set KIKI_PROVIDER or [ingest] provider in config.toml)")
    if provider not in P.PROVIDERS:
        sys.exit(f"kiki ingest: unknown provider '{provider}' (known: {', '.join(P.PROVIDERS)})")
    if not model:
        model = P.PROVIDERS[provider][1]  # provider's default model

    providers_cfg = (cfg.get("providers") or {}).get(provider, {})
    # env-var key precedence
    env_key_var = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "gemini":    "GEMINI_API_KEY",
        "ollama":    None,
    }.get(provider)
    if env_key_var and os.environ.get(env_key_var):
        providers_cfg = dict(providers_cfg)
        providers_cfg["api_key"] = os.environ[env_key_var]
    if provider == "ollama" and os.environ.get("OLLAMA_BASE_URL"):
        providers_cfg = dict(providers_cfg)
        providers_cfg["base_url"] = os.environ["OLLAMA_BASE_URL"]

    return {"provider": provider, "model": model, "provider_config": providers_cfg}


# ──────────────────────────────────────────────────────────────────────────────
# Wiki state collection
# ──────────────────────────────────────────────────────────────────────────────

def collect_wiki_state(kiki_home: Path) -> str:
    """Concatenate all wiki/*.md (and one level of subdirs) with file headers
    so the model can see the current state of the wiki in one prompt."""
    wiki = kiki_home / "wiki"
    parts = []
    for path in sorted(wiki.rglob("*.md")):
        rel = path.relative_to(wiki)
        try:
            content = path.read_text()
        except OSError:
            continue
        parts.append(f"=== wiki/{rel} ===\n{content.rstrip()}\n")
    return "\n".join(parts)


def read_claude_md(kiki_home: Path) -> str:
    p = kiki_home / "CLAUDE.md"
    if p.exists():
        return p.read_text()
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Edit application
# ──────────────────────────────────────────────────────────────────────────────

def apply_edits(kiki_home: Path, edits: list[dict]) -> list[str]:
    """Apply the model's edits to wiki/. Returns a list of human-readable
    descriptions for each applied edit."""
    wiki = kiki_home / "wiki"
    applied = []
    for e in edits:
        page = e.get("page", "")
        op = e.get("operation", "")
        if not page or "/.." in page or page.startswith("/"):
            sys.stderr.write(f"  ✗ skipping edit with bad page path: {page!r}\n")
            continue
        target = wiki / page
        target.parent.mkdir(parents=True, exist_ok=True)

        if op == "create":
            target.write_text((e.get("content") or "").rstrip() + "\n")
            applied.append(f"create {page}")
        elif op == "replace":
            target.write_text((e.get("content") or "").rstrip() + "\n")
            applied.append(f"replace {page}")
        elif op == "append":
            section = (e.get("section") or "").strip()
            content = (e.get("content") or "").rstrip()
            existing = target.read_text() if target.exists() else ""
            if section:
                heading_line = f"## {section}"
                if heading_line in existing:
                    new = re.sub(
                        rf"(^|\n)({re.escape(heading_line)}\n)",
                        rf"\1\2{content}\n\n",
                        existing,
                        count=1,
                    )
                else:
                    sep = "\n\n" if existing.strip() else ""
                    new = f"{existing.rstrip()}{sep}\n{heading_line}\n\n{content}\n"
            else:
                sep = "\n\n" if existing.strip() else ""
                new = f"{existing.rstrip()}{sep}{content}\n"
            target.write_text(new)
            applied.append(f"append {page}" + (f" §{section}" if section else ""))
        elif op == "edit":
            old = e.get("edit_old", "")
            new_text = e.get("edit_new", "")
            if not target.exists():
                sys.stderr.write(f"  ✗ edit requested but {page} doesn't exist\n")
                continue
            existing = target.read_text()
            if old not in existing:
                sys.stderr.write(f"  ✗ edit_old not found in {page} (skipping)\n")
                continue
            target.write_text(existing.replace(old, new_text, 1))
            applied.append(f"edit {page}")
        else:
            sys.stderr.write(f"  ✗ unknown operation {op!r} for {page}\n")
    return applied


def append_log(kiki_home: Path, log_entry: str) -> None:
    if not log_entry.strip():
        return
    log_path = kiki_home / "wiki" / "log.md"
    existing = log_path.read_text() if log_path.exists() else "# Log\n"
    sep = "\n\n" if existing.rstrip() else ""
    log_path.write_text(f"{existing.rstrip()}{sep}{log_entry.rstrip()}\n")


def flip_ingested_frontmatter(raw_file: Path) -> None:
    """Set `ingested: true` in the frontmatter (or insert it if missing)."""
    text = raw_file.read_text()
    if not text.startswith("---\n"):
        return
    end = text.find("\n---\n", 4)
    if end == -1:
        return
    front = text[4:end]
    body = text[end + 5:]
    if re.search(r"^ingested:\s*", front, re.M):
        front = re.sub(r"^ingested:\s*.*$", "ingested: true", front, flags=re.M)
    else:
        front = front.rstrip() + "\ningested: true"
    raw_file.write_text(f"---\n{front.rstrip()}\n---\n{body}")


# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are the ingest agent for kiki, a personal memory wiki for a software \
engineer. Your job: read a single newly-captured raw note and decide what \
edits, if any, to make to the wiki.

The wiki schema (CLAUDE.md, attached below) defines what each page is for. \
Strongly prefer updating existing pages over creating new ones. Avoid concept \
inflation — only create a new page when no existing page covers the topic.

You will receive (1) the kiki schema, (2) the current wiki state, and (3) the \
raw note. Return a single JSON object describing all edits to apply.

Conservative defaults:
- Smoke tests, signal "verify", and trivial bodies → empty page_edits, brief \
log_entry noting the no-op.
- Always cite the source raw file in any new content (e.g. "(from raw/notes/X)").
- Confidence: low unless the raw note states the claim outright.

The kiki schema (CLAUDE.md):
---
{claude_md}
---
"""


def build_user_message(wiki_state: str, raw_path: Path, raw_content: str) -> str:
    return (
        f"Current wiki state:\n\n{wiki_state}\n\n"
        f"Raw note ({raw_path}):\n\n{raw_content}\n\n"
        "Decide on edits and return the JSON plan."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def vlog(msg: str) -> None:
    if VERBOSE:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.exit("usage: ingest.py <raw_file>")

    raw_file = Path(argv[1]).resolve()
    if not raw_file.exists():
        sys.exit(f"ingest.py: no such file: {raw_file}")

    kiki_home = Path(os.environ.get("KIKI_HOME") or (Path.home() / ".kiki")).resolve()
    if not (kiki_home / "CLAUDE.md").exists():
        sys.exit(f"ingest.py: $KIKI_HOME ({kiki_home}) not initialized")

    try:
        raw_file.relative_to(kiki_home)
    except ValueError:
        sys.exit(f"ingest.py: file is not inside $KIKI_HOME ({kiki_home}): {raw_file}")

    cfg = load_config(kiki_home)
    log(f"  provider: {cfg['provider']} ({cfg['model']})")

    vlog(f"  collecting wiki state from {kiki_home}/wiki/")
    wiki_state = collect_wiki_state(kiki_home)
    claude_md = read_claude_md(kiki_home)
    raw_content = raw_file.read_text()

    system = SYSTEM_PROMPT_TEMPLATE.format(claude_md=claude_md)
    user = build_user_message(wiki_state, raw_file.relative_to(kiki_home), raw_content)

    log("  asking model for ingest plan…")
    try:
        plan, usage = P.call(cfg["provider"], cfg["model"], system, user,
                             INGEST_SCHEMA, provider_config=cfg["provider_config"])
    except P.ProviderError as e:
        sys.exit(f"  ✗ {e}")

    summary = plan.get("summary", "")
    log_entry = plan.get("log_entry", "")
    edits = plan.get("page_edits") or []

    if edits:
        applied = apply_edits(kiki_home, edits)
        for a in applied:
            log(f"  → {a}")
    else:
        log("  → no page edits")

    append_log(kiki_home, log_entry)
    if log_entry.strip():
        log(f"  → log entry: {log_entry.splitlines()[0]}")

    flip_ingested_frontmatter(raw_file)
    log(f"  → marked {raw_file.relative_to(kiki_home)} ingested:true")

    if shutil.which("qmd"):
        vlog("  running qmd update")
        rc = subprocess.run(["qmd", "update"], cwd=kiki_home,
                            capture_output=not VERBOSE).returncode
        if rc == 0:
            log("  → qmd update")
        else:
            log(f"  ✗ qmd update failed (exit {rc})")

    cost = usage.get("cost_usd", 0.0)
    in_t = usage.get("input_tokens", 0)
    out_t = usage.get("output_tokens", 0)
    log(f"  ✓ {usage_line(in_t, out_t, cost)}")
    print(summary)
    return 0


def usage_line(in_t: int, out_t: int, cost: float) -> str:
    parts = []
    if in_t or out_t:
        parts.append(f"{in_t} in / {out_t} out tokens")
    if cost:
        parts.append(f"~${cost:.4f}")
    return "done" + (" (" + ", ".join(parts) + ")" if parts else "")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
