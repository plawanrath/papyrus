#!/usr/bin/env python3
"""Slash-command dispatcher for /epub-build.

Accepts either a workdir-ish reference (path or slug) or a URL/ID. If it's a
URL/ID, fetches it into an ephemeral one-off workdir first, then runs build_epub.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import manifest as mf


ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


def is_url_or_id(arg: str) -> bool:
    if arg.startswith(("http://", "https://")):
        return True
    if ARXIV_RE.match(arg):
        return True
    if re.match(r"^10\.\d{4,9}/", arg):
        return True
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: epub_build_cmd.py <workdir-or-slug-or-url-or-id>", file=sys.stderr)
        return 2
    arg = sys.argv[1].strip()
    plugin_root = mf.papyrus_root()
    py = plugin_root / "bin" / "papyrus-python"
    scripts = plugin_root / "scripts"

    if is_url_or_id(arg) and not Path(arg).exists():
        slug = re.sub(r"[^A-Za-z0-9._-]", "-", arg).strip("-")[:40] or "oneoff"
        wd = plugin_root / "working" / f"_oneoff-{slug}"
        subprocess.check_call([
            str(py), str(scripts / "fetch_source.py"),
            "--url-or-id", arg, "--workdir", str(wd),
        ])
    else:
        wd = mf.resolve_workdir_arg(arg)

    subprocess.check_call([
        str(py), str(scripts / "build_epub.py"),
        "--workdir", str(wd),
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
