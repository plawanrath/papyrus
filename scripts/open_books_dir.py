#!/usr/bin/env python3
"""Stop hook: open the books/ folder if it was touched recently.

Fires on every conversation Stop, but only acts if at least one file under
books/ has been modified in the last FRESH_WINDOW_SEC seconds — otherwise it
no-ops silently. This avoids Finder popping every time the user finishes
*any* unrelated chat session.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import manifest as mf


FRESH_WINDOW_SEC = 120


def books_dir_fresh(books_dir: Path) -> bool:
    if not books_dir.exists():
        return False
    cutoff = time.time() - FRESH_WINDOW_SEC
    for p in books_dir.rglob("*"):
        try:
            if p.stat().st_mtime >= cutoff:
                return True
        except OSError:
            continue
    return False


def open_path(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    elif system == "Linux":
        if not subprocess.run(["xdg-open", str(path)], check=False).returncode == 0:
            pass
    elif system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]


def main() -> int:
    # Drain stdin (hooks get JSON; we don't need it but shouldn't block).
    try:
        sys.stdin.read()
    except Exception:
        pass

    books = mf.books_root()
    if books_dir_fresh(books):
        open_path(books)
    return 0


if __name__ == "__main__":
    sys.exit(main())
