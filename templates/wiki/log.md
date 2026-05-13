---
title: Log
type: log
tags: [meta]
---

# Log

Append-only chronological record. Each entry starts with `## [YYYY-MM-DD] <kind> | <title>`.

Kinds: `ingest`, `query`, `lint`, `update`, `observation`.

Quick recent-activity command: `grep "^## \[" wiki/log.md | tail -10`.

---
