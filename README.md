# papyrus

A Claude Code plugin that turns a list of arxiv papers (and other research
sources) into a Kindle-ready `.epub` book — with an editorial pipeline of
subagents doing the summarization, synthesis, and figure curation.

```
"make me a Kindle book from these arxiv IDs: 2401.12345, 2403.67890, 2406.11122"
```

papyrus follows the skill, runs the steps, and hands you a polished epub
sitting in `books/<slug>/book.epub` ready to drag onto a Kindle.

## What you get

**Skills**
- `arxiv-to-epub` — full pipeline: fetch → parallel paper-summarizer subagents
  → editorial-voice synthesis with persona → figure-curator vision pass →
  pandoc → epub → epubcheck.
- `arxiv-digest` — same pipeline through synthesis, but the output is a short
  markdown briefing. For *"what's new in X this week"* without committing to a
  full book build.
- `epub-doctor` — validate and repair any existing epub. Runs epubcheck,
  diagnoses common issues (busted nav, missing cover, MathML reflow), repairs
  in a temp dir, revalidates.
- `book-draft` — collect arxiv IDs into a working dir *without* building yet.
  Re-run to add more IDs over time, then `/epub-build` when you're ready.

**Slash commands**
- `/arxiv-fetch <id>` — download the arxiv source tarball into a scratch
  working dir. No LLM in the loop.
- `/epub-build <workdir | slug | url-or-id>` — run pandoc + epubcheck on a
  prepared workdir. Also accepts a single arxiv ID, DOI, IEEE/ACM URL, or raw
  LaTeX URL — fetches into a one-off workdir and builds.

**Subagents**
- `paper-summarizer` — structured per-paper summary (contributions, method,
  results, limitations). Invoked in parallel, one per paper, so the
  orchestrator never holds full paper text.
- `editorial-voice` — synthesis pass that produces a preface and section
  ordering. Persona-driven (default: thoughtful research curator, NYRB-essay tone).
- `figure-curator` — vision pass that decides which figures survive into the
  epub, writes alt-text, and rewrites figure references in the parsed markdown.

**Hooks**
- `Stop` — when the conversation ends and a fresh epub exists in `books/`,
  open it in **Kindle Previewer 3** (macOS, if installed) so you can review
  the rendered book immediately. Falls back to opening the `books/` folder if
  the previewer isn't available. Either way, fires a clickable notification
  pointing at Send to Kindle. (mtime check, 120s window — silent on unrelated
  chats.)
- `SubagentStop` on `editorial-voice` — desktop notification when the long
  synthesis pass completes, so you can context-switch while it runs.

## Install

### Prerequisites

You only need these before running setup:

- `python3` ≥ 3.10
- `git`, `curl`, `unzip`
- macOS: [Homebrew](https://brew.sh) / Linux: `apt` — setup uses them to install
  pandoc, a JRE, cairo, and terminal-notifier
- The Claude Code `claude` CLI on `$PATH` — required for `--persistent`

You do **not** need to install pandoc, Java, cairo, or epubcheck yourself —
`setup.sh` handles them.

**Recommended (optional):** Install
[Kindle Previewer 3](https://kdp.amazon.com/en_US/help/topic/G202131170) — a
free desktop app from Amazon that simulates rendering on every Kindle device
(Paperwhite, Scribe, Oasis, tablets). When installed, the Stop hook will open
every freshly-built epub in it automatically. See the
[Iterating with Kindle Previewer](#iterating-with-kindle-previewer) section
below for the recommended workflow.

### Three steps

**1. Clone**

```bash
git clone https://github.com/plawanrath/papyrus.git
cd papyrus
```

**2. Run setup**

```bash
./setup.sh --persistent
```

`setup.sh` is idempotent — safe to re-run any time. It will:

- create `.venv/` and install Python dependencies from `requirements.txt`
- install missing system tools via your package manager (on macOS you may be
  prompted for an admin password for the Temurin JDK cask)
- download `epubcheck` into `.tools/` and write `.papyrus.env`
- run `scripts/doctor.py` to verify every dependency resolves
- with `--persistent`: register papyrus with Claude Code (user scope) by
  running `claude plugin marketplace add "$(pwd)"` followed by
  `claude plugin install papyrus@papyrus --scope user`

Drop the `--persistent` flag if you'd rather load papyrus only on demand
per session with `claude --plugin-dir "$(pwd)"`.

**3. Restart Claude Code**

Exit any running `claude` session and start a fresh one. Plugins load at
session start, so a new session is required after first install. You should
see `papyrus@papyrus` in `claude plugin list` and the skills available as
`/papyrus:<skill>`.

### Verify

In a fresh `claude` session, try the LLM-free smoke test:

```text
/papyrus:arxiv-fetch 2401.12345
```

If it reports a path under `working/_scratch/sources/2401.12345/`, you're set.

You can re-run the install verifier outside of Claude any time:

```bash
./bin/papyrus-python scripts/doctor.py
```

### Uninstall

```bash
claude plugin uninstall papyrus@papyrus
claude plugin marketplace remove papyrus
# optional — wipe the installed deps inside the repo:
rm -rf .venv .tools .papyrus.env
```

## Usage

```text
# Full pipeline → epub in books/reading-list/book.epub
/papyrus:arxiv-to-epub 2401.12345 2403.67890 2406.11122 --name reading-list

# Collect IDs over a few days, then build later
/papyrus:book-draft 2401.12345 --name kernel-fusion
/papyrus:book-draft kernel-fusion 2403.67890 2406.11122
/papyrus:epub-build working/kernel-fusion

# Quick markdown briefing (no epub)
/papyrus:arxiv-digest 2405.11111 2406.22222 --name weekly-digest

# Fix an epub from anywhere
/papyrus:epub-doctor /path/to/some-book.epub

# LLM-free single-paper fetch
/papyrus:arxiv-fetch 2401.12345

# Build from a non-arxiv source (DOIs, IEEE/ACM, raw LaTeX)
/papyrus:epub-build https://doi.org/10.1145/3458817.3476188
```

Most papyrus output lives under:
- `books/<slug>/book.epub` — finished epub + cover.png
- `working/<slug>/manifest.json` — draft state (sources, statuses, persona)
- `cache/<arxiv-id>/` — content-addressed cache so re-fetches are free

All three are gitignored.

## Iterating with Kindle Previewer

The tightest feedback loop for tuning a book — covers, persona voice, figure
selection, TOC structure — is to preview locally before sending anything to
your Kindle. Each Send-to-Kindle round-trip takes minutes for conversion +
wireless delivery; the previewer is instant.

**Install [Kindle Previewer 3](https://kdp.amazon.com/en_US/help/topic/G202131170)**
(free from Amazon, macOS/Windows). Once installed, papyrus's Stop hook will
open every freshly-built epub in it automatically — no manual step.

**The iteration loop:**

1. `/papyrus:arxiv-to-epub <ids> --name draft-v1` — build a first cut
2. Stop hook auto-opens `books/draft-v1/book.epub` in Kindle Previewer
3. Switch the device dropdown (Paperwhite → Scribe → tablet) to spot reflow
   issues; check the TOC pane for nav correctness; verify the cover thumbnail
4. Not happy? Rebuild with a different persona, more papers, or run
   `/papyrus:epub-doctor books/draft-v1/book.epub` for structural fixes
5. Only when it's good, drag the epub onto
   [Send to Kindle](https://www.amazon.com/sendtokindle) (the Stop-hook
   notification is a clickable shortcut to that page) — the cover is already
   embedded, so don't upload `cover.png` separately

**No Kindle Previewer?** The hook falls back to opening the `books/` folder
in Finder/Explorer. Drag the `.epub` from there onto the Send-to-Kindle web
page when you're ready.

**Replacing a previous send:** Send to Kindle treats every upload as a new
personal document, so re-uploading creates a duplicate rather than updating
the existing copy (and your reading position doesn't carry over). To truly
replace, delete the old entry from
[Manage Your Content and Devices](https://www.amazon.com/hz/mycd/myx) first,
then resend.

## Personas

The editorial-voice subagent loads a persona from
`templates/personas/<persona>.md`. The default (`curator`) writes in a
NYRB-essay tone — confident, plain, throughline-first.

To add your own, drop a new file (e.g. `templates/personas/wonk.md`) and
reference it with `--persona wonk` when invoking the skill. Each book's persona
is recorded in its manifest so you can run multiple books with different voices
side-by-side.

## Extending

papyrus is built to be extended. Each pipeline stage is a separate component
that can be swapped or supplemented.

- **New skill?** Drop a folder under `skills/<your-skill>/` with a `SKILL.md`.
  See existing skills for frontmatter examples.
- **New fetcher?** (e.g. bioRxiv, OpenReview, Semantic Scholar) Extend
  `scripts/fetch_source.py`. Add a detector branch to `detect_kind()` and a
  `fetch_<thing>_branch` function that normalizes the result into
  `<workdir>/sources/<id>/`.
- **New synthesis style?** Add a persona under `templates/personas/`, or write
  a new subagent under `agents/` (e.g. `agents/critic-voice.md`) and reference
  it from a new skill.
- **Different epub style?** Edit `templates/epub.css` and
  `templates/cover.svg.j2`. Both are loaded on every build.

A rough map of which file does what:

```
.claude-plugin/plugin.json   # plugin manifest
setup.sh                     # installer
bin/papyrus-python           # venv-shim used by everything
scripts/manifest.py          # workdir/manifest data model
scripts/fetch_arxiv.py       # arxiv fetch with cache
scripts/fetch_source.py      # multi-source URL/ID sniffer + dispatcher
scripts/pandoc_to_markdown.py # paper source → markdown
scripts/build_epub.py        # markdown → epub + inline epubcheck
scripts/epub_build_cmd.py    # /epub-build dispatcher
scripts/render_cover.py      # SVG template → cover.png
scripts/epubcheck_runner.py  # epubcheck wrapper
scripts/open_books_dir.py    # Stop hook
scripts/notify.py            # SubagentStop hook
scripts/doctor.py            # install verifier
agents/                      # subagent prompts
skills/                      # skill prompts
commands/                    # flat slash-command prompts
templates/                   # epub.css, cover.svg.j2, metadata.yaml.j2, personas/
hooks/hooks.json             # Stop + SubagentStop wiring
```

## Troubleshooting

Run `./bin/papyrus-python scripts/doctor.py` first — it'll tell you what's
broken.

| Symptom | Fix |
|---|---|
| `EPUBCHECK_JAR not set` | `./setup.sh` (writes `.papyrus.env`) |
| `pandoc: command not found` | `brew install pandoc` / `apt install pandoc`, then re-run setup |
| `cairosvg: no library called "cairo-2" was found` | `brew install cairo` / `apt install libcairo2` |
| Finder didn't pop after build | The Stop hook only fires if `books/` was touched in the last 120s. Check the file is actually there. |
| No desktop notification on synthesis | `terminal-notifier` (macOS) or `notify-send` (Linux) not installed. Optional — the pipeline still runs. |
| epubcheck reports errors | Use `/papyrus:epub-doctor <path-to-epub>` to triage and repair |
| Build hangs on a DOI / IEEE paper | Those sources often need manual PDF placement. Look for `needs_manual_input: true` in the fetch output and drop the file into `<workdir>/sources/<id>/`. |

## License

Apache 2.0 — see [LICENSE](LICENSE).
