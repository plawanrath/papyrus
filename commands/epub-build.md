---
description: Build an epub from a prepared workdir, or from a single source (arxiv ID, DOI, IEEE/ACM URL, raw LaTeX URL).
argument-hint: "<workdir | slug | url-or-id>"
allowed-tools: Bash
---

Build a Kindle-ready epub. The argument can be:

- An absolute or relative path to a prepared workdir (e.g. `working/my-book/`).
- A bare slug (resolved to `working/<slug>/`).
- An arxiv ID, DOI, IEEE/ACM URL, or raw `.tex`/`.tar.gz` URL — in which case a
  fresh single-paper workdir is created on the fly.

The build runs pandoc, then epubcheck inline. Final epub lands in
`books/<slug>/book.epub` (relative to the plugin root).

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/papyrus-python" \
  "${CLAUDE_PLUGIN_ROOT}/scripts/epub_build_cmd.py" \
  "$ARGUMENTS"
```
