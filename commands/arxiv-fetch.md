---
description: Download an arxiv source tarball into a scratch working dir. No LLM in the loop.
argument-hint: "<arxiv-id>"
allowed-tools: Bash
---

Fetch the arxiv source identified by `$ARGUMENTS` into `working/_scratch/`. The
cache short-circuits any repeat download silently. After fetching, report the
resulting source path and title from the JSON output.

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/papyrus-python" \
  "${CLAUDE_PLUGIN_ROOT}/scripts/fetch_arxiv.py" \
  --id "$ARGUMENTS" \
  --workdir "${CLAUDE_PLUGIN_ROOT}/working/_scratch"
```
