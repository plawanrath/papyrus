#!/usr/bin/env python3
"""Render the cover SVG template to PNG.

Reads templates/cover.svg.j2, injects title/subtitle/byline, rasterizes via
cairosvg. Output is 1600x2560 (Kindle-friendly aspect).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jinja2 import Template

import manifest as mf


COVER_WIDTH = 1600
COVER_HEIGHT = 2560


def render(title: str, subtitle: str, byline: str, out_path: Path) -> None:
    tpl_path = mf.papyrus_root() / "templates" / "cover.svg.j2"
    tpl = Template(tpl_path.read_text(encoding="utf-8"))
    svg = tpl.render(title=title, subtitle=subtitle, byline=byline,
                     width=COVER_WIDTH, height=COVER_HEIGHT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Lazy import so doctor.py can still flag missing cairo cleanly.
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                     write_to=str(out_path),
                     output_width=COVER_WIDTH,
                     output_height=COVER_HEIGHT)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render the papyrus cover PNG")
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--byline", default="A papyrus reading list")
    ap.add_argument("--out", required=True, help="output PNG path")
    args = ap.parse_args()

    try:
        render(args.title, args.subtitle, args.byline, Path(args.out))
    except Exception as e:
        print(f"render_cover: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
