---
description: Build a narrative technical book (Kindle-ready epub) from a list of arxiv IDs. Fetches papers, summarizes them in parallel, designs a chapter outline, writes each chapter as synthesized prose (drawing on multiple papers, not reprinting them), curates figures, then assembles the epub. The output is a book that teaches the territory, not an anthology of papers.
argument-hint: "<id> [<id>...] [--name <slug>] [--persona <persona>]"
allowed-tools: Bash, Read, Write, Task
---

This is the full pipeline. Given a list of arxiv IDs (or DOIs / IEEE / ACM /
raw-LaTeX URLs), you produce a polished epub at `books/<slug>/book.epub`.

**This is NOT an anthology.** The book's body is *not* the original papers
stitched together. Chapter-writer subagents synthesize across papers to
produce narrative technical prose that teaches concepts; the original papers
appear only as References-table entries. If you find yourself appending parsed
paper markdown verbatim into the book, you've taken a wrong turn.

## Inputs

`$ARGUMENTS` contains:

- One or more arxiv IDs (or arxiv URLs).
- Optional `--name <slug>` — book slug.
- Optional `--persona <persona>` — editorial persona (default `curator`).

## Pipeline

### 1. Setup the workdir

Parse `$ARGUMENTS`. Determine the slug (use `--name` if provided; otherwise
default to `book-<YYYY-MM-DD>`). Determine the persona path:
`${CLAUDE_PLUGIN_ROOT}/templates/personas/<persona>.md`.

For each ID, run:

```bash
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
PY="$PLUGIN/bin/papyrus-python"
WD="$PLUGIN/working/<slug>"

"$PY" "$PLUGIN/scripts/fetch_source.py" \
    --url-or-id "<id>" --workdir "$WD" \
    --name "<book title>" --persona "<persona>"
```

Cache hits are silent. Read `$WD/manifest.json` to confirm sources.

### 2. Parse each paper to markdown

For each source in the manifest:

```bash
"$PY" "$PLUGIN/scripts/pandoc_to_markdown.py" --workdir "$WD" --id "<source_id>"
```

These can run sequentially in a single Bash block; pandoc is fast.

### 3. Summarize papers in parallel (paper-summarizer subagents)

**Issue N Task tool calls in a single assistant message** — one per source —
each invoking the `paper-summarizer` subagent. Each Task prompt should
include the workdir, source_id, and the path to `parsed/<id>.md`. Example:

> Summarize the paper at `<workdir>/parsed/<id>.md`. Write the structured
> result to `<workdir>/summaries/<id>.json`. The source_id is `<id>`.

Each subagent writes its own `summaries/<id>.json` to disk. Wait for all to
complete. **Do not read full paper text yourself** — the whole point of this
step is to keep paper bodies out of the orchestrator context.

### 4. Design the book outline (editorial-voice subagent — single call)

Read each `summaries/<id>.json` (small files) and inline their contents into
a single Task call to `editorial-voice`. Pass:

- `workdir` — the path.
- `persona_path` — `${CLAUDE_PLUGIN_ROOT}/templates/personas/<persona>.md`.
- `title` — book title.
- Each summary, inlined, with its source_id labeled.

editorial-voice writes:
- `build/preface.md` — the book's opening essay.
- `build/outline.json` — the chapter outline. Each chapter is a *concept*
  (not a paper), with `title`, `concept`, `sources` (the papers feeding it),
  and `transition_in`.

A paper may appear in multiple chapters' `sources`. That's expected.

### 5. Write chapters in parallel (chapter-writer subagents)

Read `build/outline.json`. **For each chapter, issue a Task call to
`chapter-writer`, all dispatched in a single assistant message.** Each Task
prompt should include:

- `workdir` — the path.
- `chapter_index` — the zero-based index of this chapter in the outline.
- `chapter` — the chapter object from outline.json (inlined as JSON).
- `persona_path` — same path as before.

Each chapter-writer reads the source papers it needs (summaries and full
parsed text via Read), then writes
`<workdir>/build/chapters/<NN>-<slug>.md`. Wait for all to complete.

This is the heaviest step — chapter-writers ingest full paper text. A
typical 5-paper book takes 5–15 minutes here.

### 6. Curate figures (figure-curator subagent — single call)

Dispatch `figure-curator` with the workdir path. It reads each chapter,
picks 0–3 figures from the chapter's source papers, and edits each chapter
file to insert the figures with alt-text and captions in-line at the right
anchor points.

### 7. Build the epub

Run:

```bash
"$PY" "$PLUGIN/scripts/build_epub.py" --workdir "$WD"
```

This assembles `build/manuscript.md` as **preface → chapters in outline
order → auto-generated References table**, rewrites inline `[<id>]` citations
into links to that table, renders the cover and metadata, runs pandoc, then
runs epubcheck inline. Output lands at `books/<slug>/book.epub`.

### 8. Report

Report the final epub path. The Stop hook auto-opens it in Kindle Previewer
(if installed) and fires a clickable notification linking to Send to Kindle.

## Important

- **In step 3, all paper-summarizer Tasks fire in one assistant message.**
  Multiple Task calls in one turn run in parallel.
- **In step 5, all chapter-writer Tasks fire in one assistant message.**
  Same parallelism trick.
- **Never inline full paper markdown into the orchestrator context.** Pass
  paths to subagents and let them Read. The orchestrator should only ever
  hold structured summaries and outline JSON.
- If `fetch_source.py` reports `needs_manual_input: true` (DOI/IEEE/ACM
  without an accessible PDF), pause and tell the user to drop the PDF/tex
  into `<source_path>/` before continuing.
- If `build_epub.py` exits non-zero due to epubcheck errors, surface the
  errors and offer to run `/epub-doctor` on the produced epub.
- Inline citations in chapters use `[<source_id>]` syntax. The build step
  rewrites each known `[<id>]` into a link to the References table at the back
  of the book, where every id is paired with a one-line description of the
  paper (pulled from the summary's `one_line` field). Unknown ids are left as
  plain text, so a typo never produces a dead link.
