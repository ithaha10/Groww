from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from src.config import ROOT, ensure_data_dirs

HTML_DIR = ROOT / "data" / "raw" / "html"
REPORT_PATH = ROOT / "data" / "raw" / "scrape_report.json"
TIMEOUT_S = 30
PAUSE_S = 0.75
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_host(host: str) -> str:
    host = (host or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def host_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = _normalize_host(urlparse(url).hostname or "")
    if not host:
        return False
    allowed = [_normalize_host(d) for d in allowed_domains]
    return any(host == d or host.endswith("." + d) for d in allowed)


def scrape_all(config: dict) -> Path:
    ensure_data_dirs()
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    allowed = list(config.get("allowed_domains") or [])
    sources = list(config.get("sources") or [])
    rows: list[dict[str, Any]] = []

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})

    for i, source in enumerate(sources):
        source_id = source.get("id") or f"source-{i}"
        url = source.get("url") or ""
        fetched_at = _utc_now()
        row: dict[str, Any] = {
            "id": source_id,
            "url": url,
            "html_path": None,
            "http_status": None,
            "fetched_at": fetched_at,
            "error": None,
        }

        if not url:
            row["error"] = "missing_url"
            rows.append(row)
            continue
        if not host_allowed(url, allowed):
            row["error"] = "domain_not_allowed"
            rows.append(row)
            continue

        try:
            response = session.get(url, timeout=TIMEOUT_S, allow_redirects=True)
            row["http_status"] = response.status_code
            if response.status_code == 200 and response.content:
                html_path = HTML_DIR / f"{source_id}.html"
                html_path.write_bytes(response.content)
                row["html_path"] = str(html_path.relative_to(ROOT).as_posix())
            else:
                row["error"] = f"http_{response.status_code}"
        except requests.Timeout:
            row["error"] = "timeout"
        except requests.RequestException as exc:
            row["error"] = f"request_error: {exc}"

        rows.append(row)
        if i < len(sources) - 1:
            time.sleep(PAUSE_S)

    ok = [r for r in rows if r.get("html_path") and not r.get("error")]
    failed = [r for r in rows if r not in ok]
    report = {
        "fetched_at": _utc_now(),
        "ok_count": len(ok),
        "failed_count": len(failed),
        "ok": ok,
        "failed": failed,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"scrape: {len(ok)} ok, {len(failed)} failed -> {REPORT_PATH.relative_to(ROOT).as_posix()}")
    return REPORT_PATH
