#!/usr/bin/env python3
"""Notification hook: send a desktop notification via terminal-notifier/notify-send.

Silent no-op when neither tool is available. Hooks should never fail the run.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys


def notify(title: str, message: str) -> None:
    system = platform.system()
    if system == "Darwin" and shutil.which("terminal-notifier"):
        subprocess.run(
            ["terminal-notifier", "-title", title, "-message", message, "-sound", "Glass"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return
    if system == "Linux" and shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", title, message],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return
    # No notifier — silent.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Papyrus")
    ap.add_argument("--message", required=True)
    args = ap.parse_args()
    # Drain stdin (hook event JSON we don't need)
    try:
        sys.stdin.read()
    except Exception:
        pass
    notify(args.title, args.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
