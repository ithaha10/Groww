from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from src.config import ROOT, ensure_data_dirs
from src.ingest.scrape import REPORT_PATH as SCRAPE_REPORT_PATH

DOCUMENTS_PATH = ROOT / "data" / "raw" / "documents.jsonl"
LOAD_REPORT_PATH = ROOT / "data" / "raw" / "load_report.json"

DROP_TAGS = ("script", "style", "nav", "footer", "noscript", "svg", "iframe")
WHITESPACE_RE = re.compile(r"[ \t]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parser() -> str:
    try:
        import lxml  # noqa: F401

        return "lxml"
    except ImportError:
        return "html.parser"


def extract_text(html: str, url: str = "") -> tuple[str, str]:
    soup = BeautifulSoup(html, _parser())
    for tag in soup(list(DROP_TAGS)):
        tag.decompose()

    title = ""
    if soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)
    elif soup.h1:
        title = soup.h1.get_text(strip=True)

    body = soup.body or soup
    raw = body.get_text("\n", strip=True)
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in raw.splitlines()]
    text = BLANK_LINES_RE.sub("\n\n", "\n".join(line for line in lines if line)).strip()
    _ = url
    return title, text


def _read_scrape_report() -> dict[str, Any]:
    if not SCRAPE_REPORT_PATH.exists():
        raise FileNotFoundError(
            f"Missing {SCRAPE_REPORT_PATH.relative_to(ROOT).as_posix()}. Run scrape first: "
            "python -m src.ingest.run --phase scrape"
        )
    return json.loads(SCRAPE_REPORT_PATH.read_text(encoding="utf-8"))


def _source_lookup(config: dict) -> dict[str, dict]:
    return {s.get("id"): s for s in (config.get("sources") or []) if s.get("id")}


def load_all(config: dict) -> Path:
    ensure_data_dirs()
    report = _read_scrape_report()
    sources = _source_lookup(config)
    ok_rows = list(report.get("ok") or [])

    documents: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in ok_rows:
        doc_id = row.get("id")
        rel_path = row.get("html_path")
        html_file = ROOT / rel_path if rel_path else None
        source = sources.get(doc_id) or {}

        if not rel_path or html_file is None or not html_file.exists():
            skipped.append(
                {
                    "id": doc_id,
                    "url": row.get("url"),
                    "error": "missing_html",
                    "html_path": rel_path,
                }
            )
            continue

        html = html_file.read_text(encoding="utf-8", errors="replace")
        title, text = extract_text(html, row.get("url") or "")
        if not text:
            skipped.append(
                {
                    "id": doc_id,
                    "url": row.get("url"),
                    "error": "empty_extract",
                    "html_path": rel_path,
                }
            )
            continue

        documents.append(
            {
                "doc_id": doc_id,
                "url": row.get("url"),
                "entity_type": source.get("entity_type"),
                "entity_id": source.get("entity_id"),
                "title": title,
                "text": text,
                "html_path": rel_path,
                "fetched_at": row.get("fetched_at"),
                "http_status": row.get("http_status"),
            }
        )

    DOCUMENTS_PATH.write_text(
        "".join(json.dumps(doc, ensure_ascii=False) + "\n" for doc in documents),
        encoding="utf-8",
    )
    load_report = {
        "loaded_at": _utc_now(),
        "ok_count": len(documents),
        "skipped_count": len(skipped),
        "ok": [{"doc_id": d["doc_id"], "url": d["url"]} for d in documents],
        "skipped": skipped,
    }
    LOAD_REPORT_PATH.write_text(json.dumps(load_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"load: {len(documents)} documents, {len(skipped)} skipped -> "
        f"{DOCUMENTS_PATH.relative_to(ROOT).as_posix()}"
    )
    return DOCUMENTS_PATH
