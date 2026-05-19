#!/usr/bin/env python3
"""Fetch an arxiv paper's source tarball and metadata.

Cache-aware: checks <plugin_root>/cache/<id>/.complete first; if present, copies
from cache into the workdir silently. Otherwise downloads from arxiv.org,
extracts, fetches metadata, and populates both cache and workdir.

Usage:
    fetch_arxiv.py --id 2401.12345 --workdir working/my-book
    fetch_arxiv.py --id 2401.12345 --workdir working/my-book --name "My Book"
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import tarfile
import time
from pathlib import Path

import feedparser
import requests

import manifest as mf


ARXIV_EPRINT_URL = "https://arxiv.org/e-print/{id}"
ARXIV_API_URL = "https://export.arxiv.org/api/query?id_list={id}"
USER_AGENT = "papyrus/0.1 (https://github.com/plawanrath/papyrus)"


def fetch_metadata(arxiv_id: str) -> dict:
    r = requests.get(ARXIV_API_URL.format(id=arxiv_id), headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    if not feed.entries:
        return {"title": arxiv_id, "authors": [], "abstract": ""}
    e = feed.entries[0]
    return {
        "title": (e.get("title") or arxiv_id).strip().replace("\n", " "),
        "authors": [a.get("name", "") for a in e.get("authors", [])],
        "abstract": (e.get("summary") or "").strip(),
        "published": e.get("published", ""),
    }


def download_tarball(arxiv_id: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = ARXIV_EPRINT_URL.format(id=arxiv_id)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True)
    r.raise_for_status()
    raw_path = dest_dir / "source.raw"
    with raw_path.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if chunk:
                fh.write(chunk)
    return raw_path


def extract_tarball(raw_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    # arxiv e-print downloads are usually gzipped tar; sometimes plain tex/pdf.
    try:
        with tarfile.open(raw_path, "r:*") as tf:
            tf.extractall(target_dir, filter="data")
        return
    except (tarfile.TarError, EOFError):
        pass
    # Not a tarball — keep as-is (likely a single .tex or .pdf)
    shutil.copy2(raw_path, target_dir / raw_path.name)


def populate_cache(arxiv_id: str) -> Path:
    """Download to cache/<id>/, return cache path. Idempotent."""
    cache_dir = mf.cache_root() / arxiv_id
    sentinel = cache_dir / ".complete"
    if sentinel.exists():
        return cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_path = download_tarball(arxiv_id, cache_dir)
    meta = fetch_metadata(arxiv_id)
    (cache_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    # Extract into a subdir to keep raw + extracted side by side.
    extract_dir = cache_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_tarball(raw_path, extract_dir)
    sentinel.write_text(mf.now_iso(), encoding="utf-8")
    return cache_dir


def copy_cache_into_workdir(arxiv_id: str, workdir: Path) -> Path:
    """Mirror cache contents into <workdir>/sources/<id>/. Returns the source dir."""
    cache_dir = mf.cache_root() / arxiv_id
    src_dir = workdir / "sources" / arxiv_id
    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True, exist_ok=True)
    extracted = cache_dir / "extracted"
    if extracted.exists():
        # Copy contents (not the 'extracted' dir itself)
        for child in extracted.iterdir():
            target = src_dir / child.name
            if child.is_dir():
                shutil.copytree(child, target)
            else:
                shutil.copy2(child, target)
    raw = cache_dir / "source.raw"
    if raw.exists():
        shutil.copy2(raw, src_dir / "source.raw")
    meta = cache_dir / "metadata.json"
    if meta.exists():
        shutil.copy2(meta, src_dir / "metadata.json")
    return src_dir


def load_cached_metadata(arxiv_id: str) -> dict:
    f = mf.cache_root() / arxiv_id / "metadata.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"title": arxiv_id, "authors": []}


def fetch_arxiv(arxiv_id: str, workdir: Path, book_name: str | None = None,
                persona: str = "curator") -> dict:
    """Top-level: ensures workdir/manifest exists, fetches (with cache), updates manifest."""
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    # Initialize manifest if needed. Slug is the workdir name.
    slug = book_name or workdir.name
    if (workdir / mf.MANIFEST_NAME).exists():
        manifest = mf.load(workdir)
    else:
        manifest = mf.new_manifest(slug, title=book_name, persona=persona)

    for sub in ("sources", "parsed", "summaries", "build"):
        (workdir / sub).mkdir(exist_ok=True)

    cache_hit = (mf.cache_root() / arxiv_id / ".complete").exists()
    populate_cache(arxiv_id)
    copy_cache_into_workdir(arxiv_id, workdir)
    meta = load_cached_metadata(arxiv_id)

    src = mf.add_source(
        manifest,
        source_id=arxiv_id,
        kind="arxiv",
        url=f"https://arxiv.org/abs/{arxiv_id}",
        title=meta.get("title", arxiv_id),
        authors=meta.get("authors", []),
    )
    src["fetched_at"] = mf.now_iso()
    src["status"] = mf.SOURCE_STATUS_FETCHED

    mf.save(workdir, manifest)

    return {
        "id": arxiv_id,
        "workdir": str(workdir),
        "source_path": str(workdir / "sources" / arxiv_id),
        "cache_hit": cache_hit,
        "title": meta.get("title", arxiv_id),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch arxiv paper into a workdir (cache-aware)")
    ap.add_argument("--id", required=True, help="arxiv identifier, e.g. 2401.12345 or 2401.12345v2")
    ap.add_argument("--workdir", required=True, help="path to working/<slug> directory")
    ap.add_argument("--name", default=None, help="book title for new workdirs")
    ap.add_argument("--persona", default="curator", help="editorial persona slug")
    ap.add_argument("--quiet", action="store_true", help="suppress stdout JSON on cache hit")
    args = ap.parse_args()

    try:
        result = fetch_arxiv(args.id, Path(args.workdir), book_name=args.name, persona=args.persona)
    except requests.HTTPError as e:
        print(f"fetch_arxiv: HTTP {e.response.status_code} for {args.id}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"fetch_arxiv: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if result["cache_hit"] and args.quiet:
        return 0
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
