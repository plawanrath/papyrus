#!/usr/bin/env python3
"""Convert a paper's source (LaTeX or PDF) into pandoc-flavored markdown.

Strategy:
  1. Look for a main .tex file (prefer one with \\documentclass).
  2. If found, run pandoc latex -> markdown with --extract-media.
  3. Else, look for a PDF and run pandoc pdf -> markdown (best-effort).

Output lands at <workdir>/parsed/<source_id>.md and figures at
<workdir>/parsed/_media/<source_id>/.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import manifest as mf


DOCUMENTCLASS_RE = re.compile(r"\\documentclass\b")


def find_main_tex(source_dir: Path) -> Path | None:
    tex_files = sorted(source_dir.rglob("*.tex"))
    if not tex_files:
        return None
    # Prefer one declaring \documentclass.
    for tex in tex_files:
        try:
            head = tex.read_text(encoding="utf-8", errors="ignore")[:8000]
        except Exception:
            continue
        if DOCUMENTCLASS_RE.search(head):
            return tex
    # Fallback: shortest path (usually main.tex / paper.tex in root)
    tex_files.sort(key=lambda p: (len(p.parts), len(p.name)))
    return tex_files[0]


def find_pdf(source_dir: Path) -> Path | None:
    pdfs = sorted(source_dir.rglob("*.pdf"))
    return pdfs[0] if pdfs else None


def run_pandoc(input_path: Path, output_path: Path, media_dir: Path,
               input_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pandoc",
        "-f", input_format,
        "-t", "gfm+tex_math_dollars+raw_html",
        "--wrap=none",
        "--extract-media", str(media_dir),
        str(input_path),
        "-o", str(output_path),
    ]
    subprocess.run(cmd, check=True)


def convert(workdir: Path, source_id: str) -> Path:
    source_dir = workdir / "sources" / source_id
    if not source_dir.exists():
        raise FileNotFoundError(f"source dir not found: {source_dir}")
    out_md = workdir / "parsed" / f"{source_id}.md"
    media_dir = workdir / "parsed" / "_media" / source_id

    tex = find_main_tex(source_dir)
    if tex:
        run_pandoc(tex, out_md, media_dir, input_format="latex")
        return out_md

    pdf = find_pdf(source_dir)
    if pdf:
        # pandoc can't read PDF natively in all versions; try the heuristic and fall back.
        try:
            run_pandoc(pdf, out_md, media_dir, input_format="pdf")
            return out_md
        except subprocess.CalledProcessError:
            pass
        # Last resort: copy a marker file pointing at the PDF.
        out_md.write_text(
            f"# {source_id}\n\n*Source is a PDF — see `sources/{source_id}/{pdf.name}`.*\n",
            encoding="utf-8",
        )
        return out_md

    raise FileNotFoundError(f"no .tex or .pdf found in {source_dir}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert paper source to markdown via pandoc")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--id", required=True, help="source id (matches manifest.sources[].id)")
    args = ap.parse_args()

    wd = Path(args.workdir).resolve()
    try:
        out = convert(wd, args.id)
    except subprocess.CalledProcessError as e:
        print(f"pandoc failed: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"pandoc_to_markdown: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # Mark progress in manifest if present.
    try:
        m = mf.load(wd)
        for s in m.get("sources", []):
            if s["id"] == args.id:
                s["parsed_path"] = f"parsed/{args.id}.md"
                break
        mf.save(wd, m)
    except FileNotFoundError:
        pass

    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
