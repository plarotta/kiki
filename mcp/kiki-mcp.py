#!/usr/bin/env python3
"""kiki-mcp — MCP server exposing kiki capture as a tool.

Run by an MCP-aware agent (Claude Code, Cursor, etc.) over stdio. Registered
in ~/.claude.json by `kiki claude install`. Query is intentionally not here —
qmd's own MCP server (`qmd mcp --collection wiki`) covers that.

Requires the `mcp` package on PyPI. Install:
    pip3 install --user mcp
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write(
        "kiki-mcp: missing dependency 'mcp'. Install with:\n"
        "  pip3 install --user mcp\n"
    )
    raise SystemExit(1)

KIKI_HOME: Final[Path] = Path(os.environ.get("KIKI_HOME") or (Path.home() / ".kiki"))
KIKI_BIN: Final[str] = shutil.which("kiki") or "kiki"

VALID_TYPES: Final[frozenset[str]] = frozenset({"note", "transcript"})
VALID_CONFIDENCE: Final[frozenset[str]] = frozenset({"", "low", "medium", "high"})

mcp = FastMCP("kiki")


@mcp.tool()
def capture(
    type: str,
    topic: str,
    content: str,
    tags: str = "",
    source: str = "",
    captured_by: str = "",
    confidence: str = "",
    related: str = "",
    participants: str = "",
    signal: str = "",
) -> str:
    """Write a note or transcript into $KIKI_HOME/raw/ with the kiki schema.

    Use whenever the user reveals a preference, gives a correction, validates
    an approach, shares a fact about themselves, or any other moment worth
    preserving across sessions.

    Args:
        type: "note" (short observation) or "transcript" (multi-turn session).
        topic: Short noun phrase; becomes part of the filename.
        content: The body of the entry.
        tags: Comma-separated tags.
        source: How this was captured (e.g. "claude-code-session", "manual").
        captured_by: Agent or user name.
        confidence: "low" | "medium" | "high" (or "").
        related: Comma-separated [[wikilinks]] to related wiki pages.
        participants: Transcripts only. Comma-separated participants.
        signal: 1-2 line hint telling the ingestor what this entry is for —
            which wiki page(s) it should update. Always write one; without it
            the ingestor has to re-derive the point from the body, which is
            slower and lossier.

    Returns:
        Absolute path of the file written.

    Raises:
        ValueError: type or confidence invalid; topic empty.
        RuntimeError: the underlying `kiki capture` call failed.
        FileNotFoundError: the `kiki` CLI is not on PATH.
    """
    if type not in VALID_TYPES:
        raise ValueError(f"type must be one of {sorted(VALID_TYPES)}; got {type!r}")
    if confidence not in VALID_CONFIDENCE:
        raise ValueError(
            f"confidence must be one of {sorted(VALID_CONFIDENCE - {''})} or empty; got {confidence!r}"
        )
    if not topic.strip():
        raise ValueError("topic is required")

    args = [KIKI_BIN, "capture", "--type", type, "--topic", topic]
    for flag, val in (
        ("--tags", tags),
        ("--source", source),
        ("--captured-by", captured_by),
        ("--confidence", confidence),
        ("--related", related),
        ("--participants", participants),
        ("--signal", signal),
    ):
        if val:
            args += [flag, val]

    try:
        result = subprocess.run(
            args,
            input=content,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "KIKI_HOME": str(KIKI_HOME)},
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"'kiki' CLI not found on PATH; install with 'brew install plarotta/tap/kiki'"
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"kiki capture failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


@mcp.tool()
def where() -> str:
    """Return $KIKI_HOME — the path to the user's wiki.

    Useful if the agent wants to read raw markdown directly (e.g., to browse
    the persona page or recent log entries) instead of going through `capture`.
    """
    return str(KIKI_HOME)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
