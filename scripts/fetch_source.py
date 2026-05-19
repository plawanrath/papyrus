#!/usr/bin/env python3
"""Dispatch a URL or ID to the right fetcher.

Recognizes:
  - bare arxiv IDs:     2401.12345, 2401.12345v2
  - arxiv URLs:         https://arxiv.org/abs/2401.12345
  - DOI strings:        10.1145/xxxx
  - doi.org URLs:       https://doi.org/10.1145/xxxx
  - IEEE Xplore URLs:   https://ieeexplore.ieee.org/document/...
  - ACM DL URLs:        https://dl.acm.org/doi/...
  - raw LaTeX URLs:     ...something.tex or ...something.tar.gz

Each branch normalizes the downloaded content into <workdir>/sources/<id>/
and updates the manifest, so the downstream pandoc step is source-agnostic.

Usage:
    fetch_source.py --url-or-id "<input>" --workdir working/<slug> [--name "Title"]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse

import requests

import manifest as mf
import fetch_arxiv


USER_AGENT = "papyrus/0.1 (https://github.com/plawanrath/papyrus)"

ARXIV_BARE_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([\w./-]+?)(?:v\d+)?(?:\.pdf)?/?$")
DOI_BARE_RE = re.compile(r"^10\.\d{4,9}/\S+$")
TEX_RE = re.compile(r"\.(tex|tar\.gz|tgz)(\?|$)", re.IGNORECASE)


def detect_kind(arg: str) -> tuple[str, str]:
    """Return (kind, normalized_id_or_url)."""
    arg = arg.strip()
    if ARXIV_BARE_RE.match(arg):
        return "arxiv", arg
    m = ARXIV_URL_RE.search(arg)
    if m:
        return "arxiv", m.group(1)
    if DOI_BARE_RE.match(arg):
        return "doi", arg
    parsed = urlparse(arg)
    host = parsed.netloc.lower()
    if "doi.org" in host:
        return "doi", parsed.path.lstrip("/")
    if "ieeexplore.ieee.org" in host:
        return "ieee", arg
    if "dl.acm.org" in host:
        return "acm", arg
    if TEX_RE.search(arg):
        return "latex_url", arg
    if parsed.scheme in ("http", "https"):
        return "latex_url", arg
    raise ValueError(f"Could not classify input: {arg!r}")


def fetch_arxiv_branch(arxiv_id: str, workdir: Path, name: str | None, persona: str) -> dict:
    return fetch_arxiv.fetch_arxiv(arxiv_id, workdir, book_name=name, persona=persona)


def fetch_doi_branch(doi: str, workdir: Path, name: str | None, persona: str) -> dict:
    """DOI: resolve metadata via Crossref; record but don't auto-download PDF.

    Many DOIs require institutional access. We record the metadata and a pointer
    to the URL; the user can drop the PDF/tex into sources/<id>/ manually, then
    /epub-build will pick it up.
    """
    # Lazy import so doctor's failure path is cleaner.
    from crossref.restful import Works
    works = Works()
    record = works.doi(doi)
    if record is None:
        raise SystemExit(f"DOI {doi!r} not found via Crossref")
    title = (record.get("title") or [doi])[0]
    authors = [
        " ".join(filter(None, [a.get("given"), a.get("family")]))
        for a in record.get("author", [])
    ] if record.get("author") else []
    source_id = mf.canonical_source_id("doi", doi)

    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    slug = name or workdir.name
    if (workdir / mf.MANIFEST_NAME).exists():
        m = mf.load(workdir)
    else:
        m = mf.new_manifest(slug, title=name, persona=persona)
    for sub in ("sources", "parsed", "summaries", "build"):
        (workdir / sub).mkdir(exist_ok=True)

    src_dir = workdir / "sources" / source_id
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "metadata.json").write_text(json.dumps({
        "title": title, "authors": authors, "doi": doi,
        "url": f"https://doi.org/{doi}",
    }, indent=2), encoding="utf-8")

    src = mf.add_source(
        m, source_id=source_id, kind="doi",
        url=f"https://doi.org/{doi}", title=title, authors=authors,
    )
    src["fetched_at"] = mf.now_iso()
    src["status"] = mf.SOURCE_STATUS_PENDING  # PDF still needed
    mf.save(workdir, m)

    return {
        "id": source_id, "workdir": str(workdir),
        "source_path": str(src_dir),
        "needs_manual_input": True,
        "title": title,
        "note": "DOI registered. Drop the paper's PDF or LaTeX source into the source_path before running /epub-build.",
    }


def fetch_publisher_url_branch(kind: str, url: str, workdir: Path,
                               name: str | None, persona: str) -> dict:
    """IEEE / ACM URLs — register a placeholder; auto-download is unreliable behind paywalls."""
    source_id = mf.canonical_source_id("doi", urlparse(url).path.strip("/") or url)
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    slug = name or workdir.name
    if (workdir / mf.MANIFEST_NAME).exists():
        m = mf.load(workdir)
    else:
        m = mf.new_manifest(slug, title=name, persona=persona)
    for sub in ("sources", "parsed", "summaries", "build"):
        (workdir / sub).mkdir(exist_ok=True)
    src_dir = workdir / "sources" / source_id
    src_dir.mkdir(parents=True, exist_ok=True)

    src = mf.add_source(m, source_id=source_id, kind=kind, url=url,
                        title=url, authors=[])
    src["fetched_at"] = mf.now_iso()
    src["status"] = mf.SOURCE_STATUS_PENDING
    mf.save(workdir, m)
    return {
        "id": source_id, "workdir": str(workdir),
        "source_path": str(src_dir),
        "needs_manual_input": True,
        "title": url,
        "note": f"{kind.upper()} URL registered. Most {kind.upper()} papers are paywalled; "
                f"drop the PDF or LaTeX source into the source_path manually before /epub-build.",
    }


def fetch_latex_url_branch(url: str, workdir: Path, name: str | None, persona: str) -> dict:
    """Direct download of a .tex or .tar.gz URL."""
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    slug = name or workdir.name
    if (workdir / mf.MANIFEST_NAME).exists():
        m = mf.load(workdir)
    else:
        m = mf.new_manifest(slug, title=name, persona=persona)
    for sub in ("sources", "parsed", "summaries", "build"):
        (workdir / sub).mkdir(exist_ok=True)

    parsed = urlparse(url)
    base = Path(parsed.path).name or "source"
    source_id = mf.canonical_source_id("latex", base.split(".")[0])
    src_dir = workdir / "sources" / source_id
    src_dir.mkdir(parents=True, exist_ok=True)

    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True)
    r.raise_for_status()
    raw_path = src_dir / base
    with raw_path.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if chunk:
                fh.write(chunk)
    # Try to untar if applicable.
    if base.endswith((".tar.gz", ".tgz")):
        try:
            with tarfile.open(raw_path, "r:*") as tf:
                tf.extractall(src_dir, filter="data")
        except tarfile.TarError:
            pass

    src = mf.add_source(m, source_id=source_id, kind="latex_url", url=url,
                        title=base, authors=[])
    src["fetched_at"] = mf.now_iso()
    src["status"] = mf.SOURCE_STATUS_FETCHED
    mf.save(workdir, m)
    return {
        "id": source_id, "workdir": str(workdir),
        "source_path": str(src_dir), "title": base,
    }


def dispatch(arg: str, workdir: Path, name: str | None = None,
             persona: str = "curator") -> dict:
    kind, normalized = detect_kind(arg)
    if kind == "arxiv":
        return fetch_arxiv_branch(normalized, workdir, name, persona)
    if kind == "doi":
        return fetch_doi_branch(normalized, workdir, name, persona)
    if kind in ("ieee", "acm"):
        return fetch_publisher_url_branch(kind, normalized, workdir, name, persona)
    if kind == "latex_url":
        return fetch_latex_url_branch(normalized, workdir, name, persona)
    raise ValueError(f"unhandled kind {kind}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch a paper from arxiv/DOI/IEEE/ACM/raw-LaTeX")
    ap.add_argument("--url-or-id", required=True, help="arxiv ID, DOI, or URL")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--name", default=None, help="book title for new workdirs")
    ap.add_argument("--persona", default="curator")
    args = ap.parse_args()

    try:
        result = dispatch(args.url_or_id, Path(args.workdir),
                          name=args.name, persona=args.persona)
    except ValueError as e:
        print(f"fetch_source: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"fetch_source: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
