---
description: Collect arxiv IDs into a draft workdir without building an epub yet. Idempotent — re-run to add more IDs to the same book.
argument-hint: "<id> [<id>...] [--name <slug>] [--persona <persona>]"
allowed-tools: Bash, Read
---

Set up (or extend) a book draft. You fetch the papers, populate the workdir,
and stop short of summarization and synthesis — leaving the user free to add
more IDs later before they're ready to build.

## Inputs

`$ARGUMENTS` contains a whitespace-separated list of arxiv IDs (or URLs), with
optional flags:

- `--name <slug>` — set the book slug (otherwise inferred from the first paper's title).
- `--persona <persona>` — editorial persona slug (default `curator`). The persona
  isn't used until synthesis, but recording it here keeps the manifest consistent.

## Steps

1. Parse `$ARGUMENTS`. Separate IDs/URLs from `--name`/`--persona` flags.
2. If `--name` is missing and the workdir doesn't already exist, fetch the
   *first* paper into a temp workdir to learn its title, then derive a slug.
   (You can do this by fetching into `working/_scratch` and reading
   `working/_scratch/manifest.json`.) Simpler: ask the user to pass `--name`
   when starting a new book; if they didn't, default to a date-based slug
   like `draft-YYYY-MM-DD`.
3. For each ID/URL, run `fetch_source.py` against `working/<slug>/`. This is
   idempotent — already-fetched IDs no-op via the cache.
4. Read back `working/<slug>/manifest.json` and report:
   - the workdir path
   - the list of sources (id, title, status)
   - what's next: either *"Add more IDs by re-running `/book-draft <slug> <new-ids>`"*
     or *"Ready — run `/epub-build working/<slug>` when you want the epub."*

## Example invocation

```bash
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
PY="$PLUGIN/bin/papyrus-python"

# For each ID:
"$PY" "$PLUGIN/scripts/fetch_source.py" \
    --url-or-id "<id>" \
    --workdir "$PLUGIN/working/<slug>" \
    --name "<book title>" \
    --persona "<persona>"

# Read and report the manifest:
cat "$PLUGIN/working/<slug>/manifest.json"
```

## Important

- Do **not** run the summarizer/editorial/figure-curator agents from here. This
  skill is fetch-only.
- Do **not** build the epub. That's `/epub-build`.
- If the user passes a slug that already exists, just append. Duplicate IDs are
  fine — `add_source` is a no-op on conflicts.
