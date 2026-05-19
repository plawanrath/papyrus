---
description: Generate a short markdown briefing from a list of arxiv IDs. Same fetch + summarize + synthesize stages as arxiv-to-epub, but output is a single markdown file, not an epub.
argument-hint: "<id> [<id>...] [--name <slug>] [--persona <persona>] [--out <path>]"
allowed-tools: Bash, Read, Write, Task
---

Lightweight version of `arxiv-to-epub`. Useful for "what's new in X this week"
without committing to a full book build. Same pipeline through synthesis, but
the artifact is markdown instead of epub.

## Inputs

`$ARGUMENTS`:

- One or more arxiv IDs (or arxiv URLs).
- Optional `--name <slug>` — workdir slug (default `digest-<YYYY-MM-DD>`).
- Optional `--persona <persona>` — editorial persona (default `curator`).
- Optional `--out <path>` — final markdown destination (default `books/<slug>/digest.md`).

## Steps

### 1. Setup workdir and fetch

Same as arxiv-to-epub steps 1–2. Use `fetch_source.py` per ID, then
`pandoc_to_markdown.py` per source.

### 2. Summarize papers in parallel

Same as arxiv-to-epub step 3: dispatch one `paper-summarizer` Task per paper,
all in a single assistant turn. Wait for completion.

### 3. Synthesize (single editorial-voice call)

Dispatch `editorial-voice` with the same inputs as arxiv-to-epub. It writes
`build/preface.md` and `build/ordering.json`. (You still want ordering even for
a digest — it shapes the section structure of the briefing.)

### 4. Assemble the briefing

Skip pandoc/epub. Read `build/preface.md` and `build/ordering.json`. Then write
the digest:

```
# <book title>

<preface body>

---

## <section 1 title>
*<transition_in>*

### <paper 1 title>
- **Contributions:** ...
- **Method:** ...
- **Key results:** ...
- **Limitations:** ...
- [arxiv link](...)

### <paper 2 title>
...

## <section 2 title>
...
```

For each paper, pull contributions/method/key_results/limitations from
`summaries/<id>.json`. Keep it tight — this is a briefing, not a textbook.
Use 1–3 bullets per field; trim ruthlessly.

Write to `--out` (default `books/<slug>/digest.md`).

### 5. Report

Report the path. No epub means no epubcheck and no Stop-hook-triggered
file-manager pop (the hook only fires when `books/` was touched in the last
120 seconds, which this satisfies). The SubagentStop notification still fires
after editorial-voice.

## Important

- This skill exists to be *fast*. Don't run figure-curator (vision pass is slow
  and figures don't render in a plain markdown digest).
- Persona still matters — the preface is the most visible part.
- If the user is iterating ("digest these, then build a book from the same
  draft"), point them at `/papyrus:arxiv-to-epub` with the same workdir.
