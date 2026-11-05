"""Vercel serverless endpoint for the Groww MF FAQ assistant.

POST /api/ask
  { "question": "...", "embedding": [384 floats] }

The browser computes the query embedding with Transformers.js
(Xenova/all-MiniLM-L6-v2); this function does cosine retrieval over the
bundled chunk matrix, applies guardrails/evidence checks, and calls Groq.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import numpy as np
import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "_data"
STATIC_DIR = BASE_DIR / "_static"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

SEBI_LINK = "https://investor.sebi.gov.in/"
AMFI_LINK = "https://www.amfiindia.com/investor"
FACTSHEET_LINK = "https://www.hdfcfund.com/mutual-funds/factsheets"
CAPITAL_GAIN_LINK = (
    "https://groww.in/help/mutual-funds/mf-others/"
    "how-to-download-capital-gain-report--50"
)

SCHEME_URLS = {
    "hdfc-large-cap-direct-growth": (
        "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    ),
    "hdfc-flexi-cap-direct-growth": (
        "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth"
    ),
    "hdfc-elss-tax-saver-direct-growth": (
        "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"
    ),
    "hdfc-mid-cap-direct-growth": (
        "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    ),
}

SCHEME_ALIASES = [
    ("hdfc-large-cap-direct-growth", ("large cap", "large-cap")),
    ("hdfc-flexi-cap-direct-growth", ("flexi cap", "flexi-cap", "equity fund")),
    ("hdfc-elss-tax-saver-direct-growth", ("elss", "tax saver", "tax-saver")),
    ("hdfc-mid-cap-direct-growth", ("mid cap", "mid-cap")),
]

FIELD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("statement", re.compile(r"capital\s*gain|statement|tax\s*proof|\b80\s*c\b|download", re.I)),
    ("expense_ratio", re.compile(r"expense\s*ratio|\bter\b|total\s+expense", re.I)),
    ("exit_load", re.compile(r"exit\s*load", re.I)),
    ("lock_in", re.compile(r"lock[\s-]?in", re.I)),
    ("min_sip", re.compile(r"min(?:imum)?[\s.]*(?:sip|investment)|sip\s+amount", re.I)),
    (
        "riskometer",
        re.compile(
            r"riskometer|risk\s+level|rated\b.{0,25}\brisk\b|"
            r"\b(?:very\s+)?(?:high|moderate|low)\s+risk\b",
            re.I,
        ),
    ),
    ("benchmark", re.compile(r"benchmark|track(?:s|ing)?\s+(?:the\s+)?index", re.I)),
]

VALUE_PATTERNS = {
    "expense_ratio": r"%|\d",
    "exit_load": r"%|redeem|within|day|year",
    "min_sip": r"₹|rs\.?\s*\d|\d",
    "lock_in": r"\d|year",
    "benchmark": r"index|nifty|sensex|total\s+return|\d",
}
DEFINITION_PHRASES = ("a fee payable", "is a fee", "refers to", "is defined as")

PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.I),
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    re.compile(r"\b(?:account|a/c|acct)\b[^0-9]{0,20}\d{9,18}\b", re.I),
    re.compile(r"\botp\b[^0-9]{0,12}\d{4,8}\b", re.I),
]

ADVICE_PATTERNS = [
    re.compile(r"\bshould\s+(?:i|we)\b", re.I),
    re.compile(r"\b(?:buy|sell|hold|switch|redeem|exit\s+from)\b", re.I),
    re.compile(r"\b(?:recommend|suggest|advice|advise)\b", re.I),
    re.compile(r"\bportfolio\b|\ballocat(?:e|ion)\b", re.I),
    re.compile(r"\bwhich\b.{0,30}\b(?:better|best)\b|\bbest\s+fund\b|\bbetter\s+fund\b", re.I),
    re.compile(r"\binvest\s+in\b", re.I),
]

RETURNS_PATTERNS = [
    re.compile(r"\breturns?\b|\bcagr\b|\bxirr\b|\bannuali[sz]ed\b", re.I),
    re.compile(r"\bperformance\b|\boutperform\b|\bbeat\s+the\b|\bbeat\s+benchmark\b", re.I),
    re.compile(r"\bcompare\b.{0,30}\b(?:return|performance|fund)\b", re.I),
    re.compile(r"\bhow\s+much\b.{0,30}\b(?:earn|grow|made)\b", re.I),
]

OTHER_AMCS = [
    "sbi", "icici", "axis", "kotak", "nippon", "franklin", "dsp", "aditya birla",
    "mirae", "tata", "uti", "quant", "parag parikh", "motilal", "bandhan",
    "canara", "idfc", "hsbc", "invesco", "loomis", "principal", "sundaram",
    "baroda", "edelweiss", "mahindra", "navi", "samco", "whiteoak", "360 one",
]

URL_RE = re.compile(r"https?://\S+", re.I)
LAST_UPDATED_RE = re.compile(r"^\s*last\s+updated\s+from\s+sources\s*:", re.I | re.M)
SOURCE_LINE_RE = re.compile(r"^\s*(?:source|citation)\s*:", re.I | re.M)

MAX_GENERAL_DISTANCE = 0.85
MAX_CONTEXT_CHUNKS = 3
MAX_CONTEXT_CHARS = 4000

SYSTEM_PROMPT = (
    "Answer only from the provided chunks. Facts only. At most three sentences. "
    "One citation URL copied from a chunk. No investment advice.\n\n"
    "You are the Groww Mutual Fund FAQ assistant. Use ONLY the retrieved chunks. "
    "If the fact is absent, say it is not in the sources; never invent numbers. "
    "Answer in at most three sentences and name the scheme and field. "
    "Do not give investment advice or return/performance claims. "
    "Do not add your own URL; the application appends one citation from the chunks."
)

_CACHE: tuple[list[dict[str, Any]], np.ndarray] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_corpus() -> tuple[list[dict[str, Any]], np.ndarray]:
    global _CACHE
    if _CACHE is None:
        chunks = [
            json.loads(line)
            for line in (DATA_DIR / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        vectors = np.load(DATA_DIR / "vectors.npy").astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        _CACHE = (chunks, vectors / norms)
    return _CACHE


def _matches(question: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(question) for pattern in patterns)


def _detect_field(question: str) -> str | None:
    for name, pattern in FIELD_PATTERNS:
        if pattern.search(question):
            return name
    return None


def _detect_entity(question: str) -> str | None:
    text = question.lower()
    for entity_id, aliases in SCHEME_ALIASES:
        if any(alias in text for alias in aliases):
            return entity_id
    return None


def check_question(question: str) -> dict[str, Any]:
    if any(pattern.search(question) for pattern in PII_PATTERNS):
        return {
            "blocked": True,
            "intent": "pii",
            "pii": True,
            "reason": "pii_detected",
            "message": (
                "I don't need personal identifiers (PAN, Aadhaar, account number, OTP, "
                "email or phone) for these FAQs, so I won't accept or store them. "
                f"Please ask a scheme-fact question or see {SEBI_LINK}."
            ),
            "url": SEBI_LINK,
        }
    if _matches(question, ADVICE_PATTERNS):
        return {
            "blocked": True,
            "intent": "advice",
            "pii": False,
            "reason": "investment_advice",
            "message": (
                "I can only share publicly available scheme facts, not investment advice. "
                f"For investor education, see {SEBI_LINK}."
            ),
            "url": SEBI_LINK,
        }
    if _matches(question, RETURNS_PATTERNS):
        return {
            "blocked": True,
            "intent": "returns",
            "pii": False,
            "reason": "performance_claims",
            "message": (
                "I can't compute or compare returns or performance. "
                f"Please use the official factsheet: {FACTSHEET_LINK}."
            ),
            "url": FACTSHEET_LINK,
        }
    lowered = question.lower()
    other = next(
        (amc for amc in OTHER_AMCS if re.search(rf"\b{re.escape(amc)}\b", lowered)), None
    )
    if other:
        return {
            "blocked": True,
            "intent": "out_of_scope",
            "pii": False,
            "reason": f"other_amc:{other}",
            "message": (
                "This demo covers HDFC Mutual Fund and four listed schemes only. "
                f"For general investor education, see {AMFI_LINK}."
            ),
            "url": AMFI_LINK,
        }
    field_name = _detect_field(question)
    return {
        "blocked": False,
        "intent": "statement" if field_name == "statement" else "fact",
        "pii": False,
        "reason": "ok",
        "field": field_name,
        "message": "",
        "url": "",
    }


def _fact_priority(field_name: str, text: str) -> int:
    text = (text or "").lower()
    if field_name == "riskometer":
        return 0 if ("rated" in text and "%" not in text) else 1
    pattern = VALUE_PATTERNS.get(field_name)
    has_value = bool(re.search(pattern, text)) if pattern else False
    is_definition = any(phrase in text for phrase in DEFINITION_PHRASES)
    return 0 if has_value and not is_definition else 1


def retrieve(
    question: str, query_embedding: list[float], top_k: int = 5
) -> dict[str, Any]:
    chunks, vectors = _load_corpus()
    query = np.asarray(query_embedding, dtype=np.float32)
    if query.ndim != 1 or query.shape[0] != vectors.shape[1]:
        raise ValueError(f"Embedding must have {vectors.shape[1]} dimensions")
    norm = float(np.linalg.norm(query)) or 1.0
    query = query / norm

    sims = vectors @ query
    order = [int(i) for i in np.argsort(-sims)]
    entity_id = _detect_entity(question)
    field_name = _detect_field(question)

    if entity_id:
        candidates = [i for i in order if chunks[i].get("entity_id") == entity_id]
        if not candidates:
            candidates = order
    else:
        candidates = order

    boosted: list[int] = []
    if entity_id and field_name and field_name != "statement":
        fact_idx = [
            i for i in candidates if (chunks[i].get("section") or "") == field_name
        ]
        fact_idx.sort(key=lambda i: (_fact_priority(field_name, chunks[i].get("text") or ""), -sims[i]))
        boosted = fact_idx[:3]

    hits: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index in boosted + candidates:
        if index in seen:
            continue
        seen.add(index)
        chunk = chunks[index]
        distance = float(1.0 - sims[index])
        hits.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "doc_id": chunk.get("doc_id"),
                "entity_id": chunk.get("entity_id"),
                "source_url": chunk.get("source_url"),
                "section": chunk.get("section"),
                "text": chunk.get("text") or "",
                "fetched_at": chunk.get("fetched_at"),
                "is_fact": bool(chunk.get("is_fact")),
                "distance": round(distance, 4),
                "score": round(float(sims[index]), 4),
            }
        )
        if len(hits) >= top_k:
            break

    return {
        "query_id": uuid.uuid4().hex[:12],
        "query": question,
        "top_k": top_k,
        "entity_filter": entity_id,
        "field_filter": field_name,
        "retrieved_at": _utc_now(),
        "hits": hits,
    }


def _hit_rank(field_name: str | None, hit: dict[str, Any]) -> tuple[int, float]:
    text = (hit.get("text") or "").lower()
    distance = hit.get("distance") if hit.get("distance") is not None else 99.0
    if field_name == "statement":
        return (0 if "capital gain" in text else 1, distance)
    if field_name == "riskometer":
        return (0 if ("rated" in text and "%" not in text) else 1, distance)
    if field_name in VALUE_PATTERNS:
        return (_fact_priority(field_name, text), distance)
    return (0 if hit.get("is_fact") else 1, distance)


def select_usable_hits(question: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    field_name = _detect_field(question)
    pattern = dict(FIELD_PATTERNS).get(field_name or "")
    usable: list[dict[str, Any]] = []
    for hit in hits:
        text = hit.get("text") or ""
        if not text.strip():
            continue
        if field_name and pattern is not None:
            if (hit.get("section") or "") == field_name or pattern.search(text):
                usable.append(hit)
        elif float(hit.get("distance") or 99.0) <= MAX_GENERAL_DISTANCE:
            usable.append(hit)
    usable.sort(key=lambda h: _hit_rank(field_name, h))
    return usable


def _best_url(config: dict | None, question: str, hits: list[dict[str, Any]]) -> str:
    field_name = _detect_field(question)
    entity_id = _detect_entity(question)
    if field_name == "statement":
        return CAPITAL_GAIN_LINK
    if entity_id and entity_id in SCHEME_URLS:
        return SCHEME_URLS[entity_id]
    for hit in hits:
        if hit.get("source_url"):
            return hit["source_url"]
    return SEBI_LINK


def _build_context(hits: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    total = 0
    for index, hit in enumerate(hits[:MAX_CONTEXT_CHUNKS], start=1):
        block = (
            f"[Chunk {index}]\n"
            f"section: {hit.get('section')}\n"
            f"source_url: {hit.get('source_url')}\n"
            f"fetched_at: {hit.get('fetched_at')}\n"
            f"text: {hit.get('text')}\n"
        )
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts).strip()


def _max_fetched_at(hits: list[dict[str, Any]]) -> str:
    values = [str(hit.get("fetched_at")) for hit in hits if hit.get("fetched_at")]
    return max(values) if values else _utc_now()


def _clean_answer(text: str) -> str:
    cleaned = URL_RE.sub("", text or "")
    cleaned = LAST_UPDATED_RE.sub("", cleaned)
    cleaned = SOURCE_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _finalize_answer(text: str, citation_url: str, last_updated: str) -> str:
    body = _clean_answer(text) or "The indexed official pages do not contain this fact."
    return f"{body}\n\nSource: {citation_url}\nLast updated from sources: {last_updated}"


def _groq(system: str, user: str) -> tuple[str | None, str | None, str]:
    api_key = os.environ.get("GROQ_API_KEY", "")
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    if not api_key:
        return None, "missing GROQ_API_KEY in Vercel environment", model
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 512,
            },
            timeout=25,
        )
    except requests.RequestException as exc:
        return None, f"Groq request failed: {exc}", model
    if response.status_code != 200:
        return None, f"Groq error {response.status_code}: {response.text[:300]}", model
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        return None, f"Unexpected Groq response: {exc}", model
    return (content or "").strip(), None, model


def refusal(
    question: str,
    query_id: str,
    reason: str,
    message: str,
    url: str,
    field: str | None = None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "query": question,
        "mode": "refuse",
        "intent": reason,
        "field": field,
        "answer_text": message,
        "citation_url": url,
        "last_updated": retrieved_at or _utc_now(),
        "chunks_used": [],
        "model": None,
        "error": None,
        "hits": [],
    }


def answer(question: str, query_embedding: list[float]) -> dict[str, Any]:
    question = (question or "").strip()
    if not question:
        return refusal("", uuid.uuid4().hex[:12], "empty", "Please enter a scheme-fact question.", SEBI_LINK)

    guard = check_question(question)
    query_id = uuid.uuid4().hex[:12]

    if guard["blocked"]:
        return refusal(
            question,
            query_id,
            guard["reason"] if guard["intent"] != "pii" else "pii",
            guard["message"],
            guard["url"],
            field=_detect_field(question),
        )

    retrieval = retrieve(question, query_embedding)
    hits = retrieval["hits"]
    usable = select_usable_hits(question, hits)

    if not usable:
        url = _best_url(None, question, hits)
        return refusal(
            question,
            query_id,
            "not_in_sources",
            f"That fact is not in the indexed official pages, so I won't guess. Please verify it here: {url}.",
            url,
            field=_detect_field(question),
            retrieved_at=retrieval["retrieved_at"],
        )

    used = usable[:MAX_CONTEXT_CHUNKS]
    field_name = _detect_field(question)
    if field_name == "statement":
        citation_url = _best_url(None, question, hits)
    else:
        citation_url = used[0].get("source_url") or _best_url(None, question, hits)
    last_updated = _max_fetched_at(used)

    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved official chunks (the only allowed evidence):\n{_build_context(used)}"
    )
    text, error, model = _groq(SYSTEM_PROMPT, user_prompt)

    public_hits = [
        {
            "chunk_id": hit.get("chunk_id"),
            "section": hit.get("section"),
            "distance": hit.get("distance"),
            "source_url": hit.get("source_url"),
            "text": hit.get("text"),
            "fetched_at": hit.get("fetched_at"),
        }
        for hit in hits
    ]

    if error:
        return {
            "query_id": query_id,
            "query": question,
            "mode": "error",
            "intent": "fact",
            "field": field_name,
            "answer_text": "",
            "citation_url": citation_url,
            "last_updated": last_updated,
            "chunks_used": [hit.get("chunk_id") for hit in used],
            "model": model,
            "error": error,
            "hits": public_hits,
        }

    return {
        "query_id": query_id,
        "query": question,
        "mode": "answer",
        "intent": "fact",
        "field": field_name,
        "answer_text": _finalize_answer(text or "", citation_url, last_updated),
        "citation_url": citation_url,
        "last_updated": last_updated,
        "chunks_used": [hit.get("chunk_id") for hit in used],
        "model": model,
        "error": None,
        "hits": public_hits,
    }


class handler(BaseHTTPRequestHandler):
    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self._headers(status, content_type, len(body))
        self.wfile.write(body)

    def _static_path(self, url_path: str) -> Path | None:
        relative = url_path.lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        candidate = (STATIC_DIR / relative).resolve()
        root = STATIC_DIR.resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate if candidate.is_file() else None

    def do_OPTIONS(self) -> None:
        self._send(200, {"ok": True})

    def do_GET(self) -> None:
        path = (self.path or "/").split("?", 1)[0]
        if path in ("/api/ask", "/api/ask/"):
            chunks, vectors = _load_corpus()
            self._send(
                200,
                {
                    "ok": True,
                    "service": "groww-mf-faq",
                    "chunks": len(chunks),
                    "dim": int(vectors.shape[1]) if len(vectors.shape) > 1 else 0,
                },
            )
            return

        static = self._static_path(path)
        if static is not None:
            self._send_bytes(
                200,
                static.read_bytes(),
                CONTENT_TYPES.get(static.suffix.lower(), "application/octet-stream"),
            )
            return

        if not path.startswith("/api/"):
            index = STATIC_DIR / "index.html"
            if index.is_file():
                self._send_bytes(200, index.read_bytes(), CONTENT_TYPES[".html"])
                return

        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = (self.path or "/").split("?", 1)[0]
        if path not in ("/api/ask", "/api/ask/"):
            self._send(404, {"mode": "error", "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            question = str(payload.get("question") or "")[:1000]
            embedding = payload.get("embedding")
            if not isinstance(embedding, list) or len(embedding) != 384:
                self._send(400, {"mode": "error", "error": "embedding must be a 384-float array"})
                return
            self._send(200, answer(question, embedding))
        except Exception as exc:
            self._send(500, {"mode": "error", "error": f"server error: {exc}"})
