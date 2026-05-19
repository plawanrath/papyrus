"""Shared workdir/manifest model.

A book draft lives at <plugin_root>/working/<slug>/, with manifest.json as the
single source of truth. All other scripts and skills read/write through here.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from slugify import slugify as _slugify


MANIFEST_NAME = "manifest.json"
STATUS_DRAFT = "draft"
STATUS_SUMMARIZED = "summarized"
STATUS_BUILT = "built"

SOURCE_STATUS_PENDING = "pending"
SOURCE_STATUS_FETCHED = "fetched"
SOURCE_STATUS_SUMMARIZED = "summarized"
SOURCE_STATUS_CURATED = "curated"
SOURCE_STATUS_FAILED = "failed"


def papyrus_root() -> Path:
    env = os.environ.get("PAPYRUS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def working_root() -> Path:
    return papyrus_root() / "working"


def books_root() -> Path:
    return papyrus_root() / "books"


def cache_root() -> Path:
    return papyrus_root() / "cache"


def workdir_for(slug: str) -> Path:
    return working_root() / slug


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str, max_length: int = 60) -> str:
    return _slugify(text, max_length=max_length) or "untitled"


def canonical_source_id(kind: str, raw: str) -> str:
    """Normalize a source identifier so it's filesystem-safe and stable."""
    if kind == "arxiv":
        return raw.strip().replace("/", "_")
    if kind == "doi":
        return "doi-" + raw.strip().lower().replace("/", "-").replace(".", "-")
    return slugify(raw)


@dataclass
class Workdir:
    path: Path
    manifest: dict[str, Any]

    @property
    def slug(self) -> str:
        return self.manifest["slug"]

    def sources_dir(self) -> Path:
        return self.path / "sources"

    def parsed_dir(self) -> Path:
        return self.path / "parsed"

    def summaries_dir(self) -> Path:
        return self.path / "summaries"

    def build_dir(self) -> Path:
        return self.path / "build"

    def ensure_subdirs(self) -> None:
        for sub in (self.sources_dir(), self.parsed_dir(), self.summaries_dir(), self.build_dir()):
            sub.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        save(self.path, self.manifest)

    def find_source(self, source_id: str) -> dict[str, Any] | None:
        for s in self.manifest.get("sources", []):
            if s["id"] == source_id:
                return s
        return None


def new_manifest(slug: str, title: str | None = None, persona: str = "curator") -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title or slug.replace("-", " ").title(),
        "created_at": now_iso(),
        "status": STATUS_DRAFT,
        "editorial_persona": persona,
        "sources": [],
        "synthesis": {
            "preface_path": "build/preface.md",
            "ordering_path": "build/ordering.json",
            "figures_curated": False,
        },
    }


def load(workdir: Path) -> dict[str, Any]:
    f = workdir / MANIFEST_NAME
    with f.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save(workdir: Path, manifest: dict[str, Any]) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    f = workdir / MANIFEST_NAME
    tmp = f.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=False)
        fh.write("\n")
    tmp.replace(f)


def open_or_create(slug: str, title: str | None = None, persona: str = "curator") -> Workdir:
    wd = workdir_for(slug)
    if (wd / MANIFEST_NAME).exists():
        m = load(wd)
    else:
        m = new_manifest(slug, title=title, persona=persona)
        save(wd, m)
    w = Workdir(path=wd, manifest=m)
    w.ensure_subdirs()
    return w


def add_source(manifest: dict[str, Any], *, source_id: str, kind: str, url: str = "",
               title: str = "", authors: list[str] | None = None) -> dict[str, Any]:
    """Idempotently add a source. Returns the source dict (existing or newly created)."""
    for s in manifest.get("sources", []):
        if s["id"] == source_id:
            return s
    entry = {
        "id": source_id,
        "kind": kind,
        "url": url,
        "title": title,
        "authors": authors or [],
        "fetched_at": None,
        "source_path": f"sources/{source_id}/",
        "parsed_path": f"parsed/{source_id}.md",
        "summary_path": f"summaries/{source_id}.json",
        "status": SOURCE_STATUS_PENDING,
    }
    manifest.setdefault("sources", []).append(entry)
    return entry


def mark_source(manifest: dict[str, Any], source_id: str, **fields: Any) -> dict[str, Any]:
    for s in manifest.get("sources", []):
        if s["id"] == source_id:
            s.update(fields)
            return s
    raise KeyError(f"source {source_id!r} not in manifest")


def resolve_workdir_arg(arg: str) -> Path:
    """Accept either an absolute/relative path or a bare slug, return the workdir path."""
    p = Path(arg)
    if p.is_absolute() or p.exists():
        return p.resolve()
    return workdir_for(arg)
