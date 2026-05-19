#!/usr/bin/env python3
"""Wrapper around the W3C epubcheck jar.

Reads $EPUBCHECK_JAR (set by setup.sh via .papyrus.env). Returns a structured
report; exits non-zero if epubcheck reports any errors.

Usage:
    epubcheck_runner.py <epub-path>
    epubcheck_runner.py <epub-path> --json     # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def epubcheck_jar() -> Path:
    env = os.environ.get("EPUBCHECK_JAR")
    if not env:
        raise SystemExit("EPUBCHECK_JAR not set. Run ./setup.sh first.")
    p = Path(env)
    if not p.is_file():
        raise SystemExit(f"EPUBCHECK_JAR not found at {p}")
    return p


def run(epub_path: Path) -> dict:
    jar = epubcheck_jar()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)
    try:
        cmd = ["java", "-jar", str(jar), "--quiet", "--json", str(report_path), str(epub_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        report = {}
        if report_path.exists() and report_path.stat().st_size > 0:
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report = {"raw": report_path.read_text(encoding="utf-8", errors="replace")}
        result = {
            "epub": str(epub_path),
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "report": report,
            "messages": report.get("messages", []) if isinstance(report, dict) else [],
        }
        return result
    finally:
        try:
            report_path.unlink()
        except OSError:
            pass


def summarize(result: dict) -> str:
    msgs = result.get("messages", [])
    if not msgs:
        return "epubcheck: no issues" if result["exit_code"] == 0 else f"epubcheck: exit {result['exit_code']}"
    by_severity: dict[str, int] = {}
    samples: list[str] = []
    for m in msgs:
        sev = (m.get("severity") or "INFO").upper()
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if sev in ("ERROR", "FATAL") and len(samples) < 5:
            sample = f"  {sev} {m.get('ID', '')}: {m.get('message', '').splitlines()[0]}"
            samples.append(sample)
    counts = ", ".join(f"{k}: {v}" for k, v in sorted(by_severity.items()))
    out = [f"epubcheck: {counts}"]
    out.extend(samples)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run epubcheck on an .epub file")
    ap.add_argument("epub", help="path to .epub")
    ap.add_argument("--json", action="store_true", help="emit full JSON report")
    args = ap.parse_args()

    epub = Path(args.epub)
    if not epub.is_file():
        print(f"epubcheck_runner: file not found: {epub}", file=sys.stderr)
        return 2

    result = run(epub)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(summarize(result))

    has_errors = any(
        (m.get("severity") or "").upper() in ("ERROR", "FATAL")
        for m in result.get("messages", [])
    )
    if has_errors or result["exit_code"] not in (0, 1):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
