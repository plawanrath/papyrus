#!/usr/bin/env python3
"""Assemble a workdir into a Kindle-ready epub via pandoc; run epubcheck inline.

Reads <workdir>/manifest.json, finds the assembled manuscript (build/manuscript.md
or auto-concats parsed/*.md + preface), renders cover.png and metadata.yaml from
templates, runs pandoc, then epubcheck.

Usage:
    build_epub.py --workdir working/my-book
    build_epub.py --workdir working/my-book --output books/my-book/book.epub
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Template

import manifest as mf
import epubcheck_runner
import render_cover


def assemble_manuscript(wd: mf.Workdir) -> Path:
    """Produce build/manuscript.md by concatenating preface + ordered parsed sections.

    If build/manuscript.md already exists (created by a higher-level skill), keep it.
    """
    out = wd.build_dir() / "manuscript.md"
    if out.exists() and out.stat().st_size > 0:
        return out

    pieces: list[str] = []
    preface = wd.build_dir() / "preface.md"
    if preface.exists():
        pieces.append(preface.read_text(encoding="utf-8").rstrip() + "\n")

    ordering_path = wd.build_dir() / "ordering.json"
    ordering = None
    if ordering_path.exists():
        try:
            ordering = json.loads(ordering_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ordering = None

    if ordering and isinstance(ordering.get("sections"), list):
        for section in ordering["sections"]:
            title = section.get("title", "").strip()
            theme = section.get("theme", "").strip()
            transition = section.get("transition_in", "").strip()
            if title:
                pieces.append(f"\n# {title}\n")
            if transition:
                pieces.append(transition + "\n")
            elif theme:
                pieces.append(f"*{theme}*\n")
            for pid in section.get("papers", []):
                _append_paper(pieces, wd, pid)
    else:
        # No editorial ordering yet — fall back to manifest order.
        for src in wd.manifest.get("sources", []):
            _append_paper(pieces, wd, src["id"])

    out.write_text("\n".join(pieces), encoding="utf-8")
    return out


def _append_paper(pieces: list[str], wd: mf.Workdir, source_id: str) -> None:
    parsed = wd.parsed_dir() / f"{source_id}.md"
    if not parsed.exists():
        pieces.append(f"\n## {source_id}\n\n*(source not yet parsed)*\n")
        return
    src = wd.find_source(source_id) or {}
    title = src.get("title") or source_id
    authors = ", ".join(src.get("authors", []) or [])
    pieces.append(f"\n## {title}\n")
    if authors:
        pieces.append(f"*{authors}*\n")
    if src.get("url"):
        pieces.append(f"\n[{src['url']}]({src['url']})\n")
    pieces.append("")
    pieces.append(parsed.read_text(encoding="utf-8").strip() + "\n")


def render_metadata(wd: mf.Workdir) -> Path:
    tpl_path = mf.papyrus_root() / "templates" / "metadata.yaml.j2"
    authors_set: list[str] = []
    seen = set()
    for s in wd.manifest.get("sources", []):
        for a in s.get("authors", []):
            if a and a not in seen:
                seen.add(a)
                authors_set.append(a)
    description = f"A curated reading list of {len(wd.manifest.get('sources', []))} papers compiled by papyrus."
    rendered = Template(tpl_path.read_text(encoding="utf-8")).render(
        title=wd.manifest.get("title") or wd.slug,
        subtitle=wd.manifest.get("subtitle", ""),
        authors=authors_set or ["Various"],
        date=wd.manifest.get("created_at", "").split("T")[0],
        description=description,
    )
    out = wd.build_dir() / "metadata.yaml"
    out.write_text(rendered, encoding="utf-8")
    return out


def render_cover_png(wd: mf.Workdir) -> Path:
    out = wd.build_dir() / "cover.png"
    title = wd.manifest.get("title") or wd.slug
    subtitle = wd.manifest.get("subtitle", "")
    byline = "A papyrus reading list"
    render_cover.render(title, subtitle, byline, out)
    return out


def pandoc_build(manuscript: Path, metadata: Path, cover: Path,
                 output: Path) -> None:
    css = mf.papyrus_root() / "templates" / "epub.css"
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pandoc",
        str(manuscript),
        "-o", str(output),
        "--toc", "--toc-depth=2",
        "--metadata-file", str(metadata),
        "--epub-cover-image", str(cover),
        "--css", str(css),
        "--resource-path", f"{manuscript.parent}:{manuscript.parent.parent}",
        "--standalone",
    ]
    subprocess.run(cmd, check=True)


def build(workdir: Path, output: Path | None = None) -> Path:
    if not (workdir / mf.MANIFEST_NAME).exists():
        raise SystemExit(f"manifest.json not found in {workdir}")
    m = mf.load(workdir)
    wd = mf.Workdir(path=workdir, manifest=m)
    wd.ensure_subdirs()

    manuscript = assemble_manuscript(wd)
    metadata = render_metadata(wd)
    cover = render_cover_png(wd)

    if output is None:
        out_dir = mf.books_root() / wd.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / "book.epub"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    pandoc_build(manuscript, metadata, cover, output)

    # Also drop a copy of the cover alongside the epub.
    try:
        shutil.copy2(cover, output.parent / "cover.png")
    except shutil.SameFileError:
        pass

    # Inline epubcheck.
    print(f"built: {output}")
    result = epubcheck_runner.run(output)
    print(epubcheck_runner.summarize(result))
    has_errors = any(
        (msg.get("severity") or "").upper() in ("ERROR", "FATAL")
        for msg in result.get("messages", [])
    )
    if has_errors:
        raise SystemExit(f"epubcheck reported errors for {output}")

    # Mark manifest as built.
    m["status"] = mf.STATUS_BUILT
    m["built_at"] = mf.now_iso()
    m["output_path"] = str(output)
    mf.save(workdir, m)

    return output


def main() -> int:
    ap = argparse.ArgumentParser(description="Build epub from a prepared workdir")
    ap.add_argument("--workdir", required=True, help="path to working/<slug>")
    ap.add_argument("--output", default=None, help="explicit output path (default: books/<slug>/book.epub)")
    args = ap.parse_args()

    wd = mf.resolve_workdir_arg(args.workdir)
    out_path = Path(args.output) if args.output else None
    try:
        result = build(wd, out_path)
    except subprocess.CalledProcessError as e:
        print(f"pandoc failed: {e}", file=sys.stderr)
        return 2
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1
    print(str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
