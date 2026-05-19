#!/usr/bin/env python3
"""Stop hook: when a fresh epub exists under books/, open it for review.

Preference order:
  1. macOS + Kindle Previewer 3 installed → open the freshest epub in it.
  2. Anything else → open the books/ folder in the OS file manager.

Either way, also fire a desktop notification (if a notifier is installed)
pointing at the Send-to-Kindle web upload URL so the user can drag-drop the
final epub onto a Kindle.

Fires on every conversation Stop, but only acts when something under books/
has been modified in the last FRESH_WINDOW_SEC seconds. That keeps the hook
silent across unrelated chat sessions.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import manifest as mf


FRESH_WINDOW_SEC = 120
SEND_TO_KINDLE_URL = "https://www.amazon.com/sendtokindle"
KINDLE_PREVIEWER_MAC_PATHS = (
    Path("/Applications/Kindle Previewer 3.app"),
    Path.home() / "Applications" / "Kindle Previewer 3.app",
)


def freshest_epub(books_dir: Path, cutoff: float) -> Path | None:
    if not books_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for p in books_dir.rglob("*.epub"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            candidates.append((mtime, p))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def books_dir_fresh(books_dir: Path, cutoff: float) -> bool:
    if not books_dir.exists():
        return False
    for p in books_dir.rglob("*"):
        try:
            if p.stat().st_mtime >= cutoff:
                return True
        except OSError:
            continue
    return False


def kindle_previewer_installed_mac() -> Path | None:
    for p in KINDLE_PREVIEWER_MAC_PATHS:
        if p.exists():
            return p
    return None


def open_in_kindle_previewer_mac(epub: Path) -> bool:
    if platform.system() != "Darwin":
        return False
    if kindle_previewer_installed_mac() is None:
        return False
    result = subprocess.run(
        ["open", "-a", "Kindle Previewer 3", str(epub)],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def open_path_in_file_manager(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif system == "Linux":
        subprocess.run(["xdg-open", str(path)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]


def notify_send_to_kindle(opened_in_previewer: bool) -> None:
    """Fire a desktop notification with the Send-to-Kindle URL.

    On macOS with terminal-notifier, the notification is clickable and opens
    the URL directly. On Linux with notify-send, the URL is shown in the body.
    """
    system = platform.system()
    if opened_in_previewer:
        msg = "Click to upload to your Kindle when ready"
    else:
        msg = "Drag the epub from books/ to upload to your Kindle"
    if system == "Darwin" and shutil.which("terminal-notifier"):
        subprocess.run(
            [
                "terminal-notifier",
                "-title", "Papyrus",
                "-subtitle", "Book ready",
                "-message", msg,
                "-open", SEND_TO_KINDLE_URL,
                "-sound", "Glass",
            ],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif system == "Linux" and shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "Papyrus — book ready",
             f"{msg}\n{SEND_TO_KINDLE_URL}"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def main() -> int:
    # Drain stdin (hook event JSON we don't need).
    try:
        sys.stdin.read()
    except Exception:
        pass

    cutoff = time.time() - FRESH_WINDOW_SEC
    books = mf.books_root()

    if not books_dir_fresh(books, cutoff):
        return 0

    epub = freshest_epub(books, cutoff)
    opened_in_previewer = False
    if epub is not None and platform.system() == "Darwin":
        opened_in_previewer = open_in_kindle_previewer_mac(epub)
    if not opened_in_previewer:
        # Fall back: open the books/ folder so the user can drag the epub.
        open_path_in_file_manager(books)

    notify_send_to_kindle(opened_in_previewer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
