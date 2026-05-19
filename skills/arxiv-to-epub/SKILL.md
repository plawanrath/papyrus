---
description: Build a Kindle-ready epub from a list of arxiv IDs. Fetches, summarizes papers in parallel via subagents, synthesizes with an editorial voice, curates figures, then assembles the epub.
argument-hint: "<id> [<id>...] [--name <slug>] [--persona <persona>]"
allowed-tools: Bash, Read, Write, Task
---

This is the full pipeline. Given a list of arxiv IDs, you produce a polished
epub in `books/<slug>/book.epub`. Subagents do the heavy lifting; the
orchestrator's context only holds structured summaries, never full paper text.

## Inputs

`$ARGUMENTS` contains:

- One or more arxiv IDs (or arxiv URLs).
- Optional `--name <slug>` — book slug.
- Optional `--persona <persona>` — editorial persona (default `curator`).

## Steps

### 1. Setup the workdir

Parse `$ARGUMENTS`. Determine the slug (use `--name` if provided; otherwise
default to `book-<YYYY-MM-DD>`). For each ID, run:

```bash
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
PY="$PLUGIN/bin/papyrus-python"
WD="$PLUGIN/working/<slug>"

"$PY" "$PLUGIN/scripts/fetch_source.py" \
    --url-or-id "<id>" --workdir "$WD" \
    --name "<book title>" --persona "<persona>"
```

Cache hits are silent. Read `$WD/manifest.json` once to confirm sources.

### 2. Parse each paper to markdown

For each source in the manifest (or just the freshly-fetched ones, if
re-running on a draft):

```bash
"$PY" "$PLUGIN/scripts/pandoc_to_markdown.py" --workdir "$WD" --id "<source_id>"
```

These can be run in a single Bash block sequentially; pandoc is fast.

### 3. Summarize papers in parallel (subagent dispatch)

**This is the critical step for keeping the orchestrator's context lean.**
Issue **N Task tool calls in a single assistant message** — one per source —
each invoking the `paper-summarizer` subagent. Each Task prompt should include
the workdir, source_id, and the path to `parsed/<id>.md`. Example prompt body:

> Summarize the paper at `<workdir>/parsed/<id>.md`. Write the result to
> `<workdir>/summaries/<id>.json` using the structured schema. The source_id is
> `<id>`. Return one line confirming.

Wait for all subagent calls to complete. Each writes its own
`summaries/<id>.json` directly to disk; you don't need to read their return
values beyond the confirmation lines.

### 4. Synthesize with editorial-voice (single subagent call)

Read each `summaries/<id>.json` (small files), inline their contents into a
single Task call to `editorial-voice`. Pass:
- The workdir path.
- The persona slug (resolves to `${CLAUDE_PLUGIN_ROOT}/templates/personas/<persona>.md`).
- The book title.
- The contents of every summary, inlined.

editorial-voice writes `build/preface.md` and `build/ordering.json`.

### 5. Curate figures (single subagent call)

Dispatch `figure-curator` with the workdir path. It reads the ordering JSON,
walks the available images, decides what survives, writes `build/figures.json`,
and rewrites figure references in `parsed/*.md`.

### 6. Build the epub

Run:

```bash
"$PY" "$PLUGIN/scripts/build_epub.py" --workdir "$WD"
```

This assembles `build/manuscript.md` from preface + ordered parsed sections,
renders cover + metadata, runs pandoc, then runs epubcheck inline. Output lands
at `books/<slug>/book.epub`.

### 7. Report

Report the final epub path. The Stop hook will pop open the books folder when
the conversation ends, and the SubagentStop hook fires terminal-notifier when
editorial-voice finishes (so the user can context-switch during synthesis).

## Important

- In step 3, **dispatch all paper-summarizer Tasks in a single message**.
  Multiple Task calls in one assistant turn run in parallel.
- Never inline full paper markdown into the orchestrator context. The subagent
  reads it from disk; you read the small JSON summary back, not the paper.
- If `fetch_source.py` reports `needs_manual_input: true` (DOI/IEEE/ACM
  without an accessible PDF), pause and tell the user to drop the PDF/tex
  into `<source_path>/` before proceeding. Do not try to summarize an empty
  source.
- If `build_epub.py` exits non-zero due to epubcheck errors, surface the
  errors and offer to run `/epub-doctor` on the produced epub.
