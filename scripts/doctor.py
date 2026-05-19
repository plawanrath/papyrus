#!/usr/bin/env python3
"""Diagnostic: verify all papyrus dependencies are reachable.

Run with bin/papyrus-python so .papyrus.env is sourced and the venv is active.
Exits non-zero if any required dependency is missing.
"""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}✓{RESET} {label}{(' — ' + detail) if detail else ''}")


def fail(label: str, detail: str = "") -> None:
    print(f"  {RED}✗{RESET} {label}{(' — ' + detail) if detail else ''}")


def warn(label: str, detail: str = "") -> None:
    print(f"  {YELLOW}!{RESET} {label}{(' — ' + detail) if detail else ''}")


def check_python_packages() -> bool:
    print("Python packages:")
    pkgs = [
        ("requests", "requests"),
        ("feedparser", "feedparser"),
        ("yaml", "pyyaml"),
        ("jinja2", "jinja2"),
        ("slugify", "python-slugify"),
        ("crossref.restful", "crossrefapi"),
        ("cairosvg", "cairosvg"),
    ]
    all_ok = True
    for mod, dist in pkgs:
        try:
            importlib.import_module(mod)
            ok(dist)
        except Exception as e:
            fail(dist, f"import failed: {e}")
            all_ok = False
    return all_ok


def check_command(cmd: str, version_args: list[str]) -> bool:
    if not shutil.which(cmd):
        fail(cmd, "not on PATH")
        return False
    try:
        out = subprocess.check_output([cmd, *version_args], stderr=subprocess.STDOUT, timeout=10)
        first = out.decode("utf-8", errors="replace").splitlines()[0]
        ok(cmd, first.strip())
        return True
    except subprocess.CalledProcessError as e:
        fail(cmd, f"exit {e.returncode}")
        return False
    except Exception as e:
        fail(cmd, str(e))
        return False


def check_epubcheck() -> bool:
    jar = os.environ.get("EPUBCHECK_JAR")
    if not jar:
        fail("epubcheck", "EPUBCHECK_JAR not set (run setup.sh)")
        return False
    if not Path(jar).is_file():
        fail("epubcheck", f"jar not found at {jar}")
        return False
    try:
        out = subprocess.check_output(
            ["java", "-jar", jar, "--version"],
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        ok("epubcheck", out.decode("utf-8", errors="replace").splitlines()[0].strip())
        return True
    except Exception as e:
        fail("epubcheck", str(e))
        return False


def check_notifier() -> None:
    print("Notifier (optional):")
    system = platform.system()
    if system == "Darwin":
        if shutil.which("terminal-notifier"):
            ok("terminal-notifier")
        else:
            warn("terminal-notifier", "not installed; notification hook will no-op")
    elif system == "Linux":
        if shutil.which("notify-send"):
            ok("notify-send")
        else:
            warn("notify-send", "not installed; notification hook will no-op")
    else:
        warn("notifier", f"unsupported platform {system}")


def main() -> int:
    print(f"Papyrus doctor — Python {sys.version.split()[0]} on {platform.system()}\n")

    pyok = check_python_packages()
    print("\nSystem tools:")
    pandok = check_command("pandoc", ["--version"])
    javok = check_command("java", ["-version"])
    print()
    epcok = check_epubcheck()
    print()
    check_notifier()

    print()
    if pyok and pandok and javok and epcok:
        print(f"{GREEN}All required dependencies are present.{RESET}")
        return 0
    print(f"{RED}One or more required dependencies are missing. Re-run ./setup.sh.{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
