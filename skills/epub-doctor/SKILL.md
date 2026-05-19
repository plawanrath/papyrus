---
description: Validate and repair an existing epub. Runs epubcheck, then fixes common issues — busted nav, re-flow math, regenerate cover.
argument-hint: "<path-to-epub>"
allowed-tools: Bash, Read, Write, Edit
---

Standalone repair tool. Works on any epub — papyrus-generated or not.
Useful when an epub from elsewhere misbehaves on Kindle.

## Inputs

`$ARGUMENTS` — path to an `.epub` file.

## Steps

### 1. Initial validation

```bash
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
PY="$PLUGIN/bin/papyrus-python"

"$PY" "$PLUGIN/scripts/epubcheck_runner.py" "$ARGUMENTS" --json > /tmp/papyrus-doctor-report.json
```

Read `/tmp/papyrus-doctor-report.json`. Look at `messages[]` — group by
`severity` (FATAL/ERROR/WARNING/USAGE/INFO) and by `ID`. Surface the top
issues to the user.

### 2. Diagnose

Common issues and how to recognize them in epubcheck output:

| Issue | epubcheck signal |
|---|---|
| Busted nav.xhtml | `RSC-005` mentioning nav, `OPF-031`, missing toc entries |
| Missing/broken cover | `OPF-014`, `OPF-072`, no `cover-image` property |
| Bad MathML | `RSC-016`, `HTM-004` near `<math>` elements |
| Resource not found | `RSC-007` (file missing in OPF manifest) |
| Encoding errors | `CSS-008`, `RSC-014` |

### 3. Repair

For each issue you can address:

- **Unpack** the epub to a working directory:
  ```bash
  TMP=$(mktemp -d -t papyrus-doctor.XXXXXX)
  cd "$TMP" && unzip -q "$ARGUMENTS"
  ```
- **nav.xhtml fixes**: Read the existing nav, identify what's wrong (missing
  entries, malformed XHTML, wrong order), and rewrite it with Edit/Write. The
  EPUB3 nav format requires a `<nav epub:type="toc">` containing an ordered
  list pointing at every spine item.
- **Cover regen**: If the cover is missing or broken, run:
  ```bash
  "$PY" "$PLUGIN/scripts/render_cover.py" \
      --title "<title from OPF metadata>" --out cover.png
  ```
  Then ensure the OPF references it correctly:
  `<item id="cover-img" href="cover.png" media-type="image/png" properties="cover-image"/>`.
- **MathML reflow**: Kindle's renderer is finicky. Convert problematic
  `<math>` blocks to images (or to plain text fallbacks) — flag this with the
  user before doing it, since it changes the rendering.
- **Missing resources**: For RSC-007, either add the file back or strip the
  manifest entry pointing at it.

- **Repack**:
  ```bash
  cd "$TMP"
  # mimetype must be the first entry and uncompressed
  zip -X0 "$ARGUMENTS.fixed" mimetype
  zip -Xur9 "$ARGUMENTS.fixed" . -x mimetype
  ```

### 4. Revalidate

```bash
"$PY" "$PLUGIN/scripts/epubcheck_runner.py" "$ARGUMENTS.fixed"
```

If clean (or at least fewer errors), report success and the path to the fixed
epub. Don't overwrite the original unless the user explicitly asks.

## Important

- Always work in a temp directory. Never modify the original epub in place.
- `zip -X0` (store-not-deflate) on `mimetype` is required by the epub spec.
- If you can't diagnose a specific issue, dump the relevant epubcheck messages
  verbatim and ask the user how they want to proceed. Don't silently leave
  errors in the output.
