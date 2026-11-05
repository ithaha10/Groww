"""Evidence check + grounded answer generation (Groq), with persisted output."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.config import ROOT
from src.query.guardrails import (
    FACTSHEET_LINK,
    FIELD_PATTERNS,
    SEBI_LINK,
    detect_field,
)
from src.query.llm.base import LLMClient, LLMResult
from src.query.llm.groq import GroqClient
from src.query.retrieve import detect_entity, scheme_url

GENERATED_DIR = ROOT / "data" / "generated"
SYSTEM_PROMPT_PATH = ROOT / "src" / "prompts" / "system.md"

MAX_GENERAL_DISTANCE = 0.85
MAX_CONTEXT_CHUNKS = 3
MAX_CONTEXT_CHARS = 4000
URL_RE = re.compile(r"https?://\S+", re.I)
LAST_UPDATED_RE = re.compile(r"^\s*last\s+updated\s+from\s+sources\s*:", re.I | re.M)
SOURCE_LINE_RE = re.compile(r"^\s*(?:source|citation)\s*:", re.I | re.M)


class _StubClient(LLMClient):
    def __init__(self, provider: str):
        self.provider = provider

    def generate(
        self, system: str, user: str, context_chunks: list[dict[str, Any]]
    ) -> LLMResult:
        return LLMResult(
            "",
            self.provider,
            error=f"LLM provider '{self.provider}' is not implemented (prototype supports groq)",
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _system_prompt() -> str:
    base = ""
    if SYSTEM_PROMPT_PATH.exists():
        base = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    rules = (
        "You are the Groww Mutual Fund FAQ assistant. Use ONLY the retrieved chunks. "
        "If the fact is absent, say it is not in the sources; never invent numbers. "
        "Answer in at most three sentences and name the scheme and field. "
        "Do not give investment advice or return/performance claims. "
        "Do not add your own URL; the application appends one citation from the chunks."
    )
    return f"{base}\n\n{rules}".strip()


def _field_pattern(field_name: str | None):
    for name, pattern in FIELD_PATTERNS:
        if name == field_name:
            return pattern
    return None


def select_usable_hits(question: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    field_name = detect_field(question)
    pattern = _field_pattern(field_name)
    usable: list[dict[str, Any]] = []
    for hit in hits:
        text = hit.get("text") or ""
        if not text.strip():
            continue
        section = (hit.get("section") or "").lower()
        if field_name and pattern is not None:
            if section == field_name or pattern.search(text):
                usable.append(hit)
        else:
            distance = hit.get("distance")
            if distance is None or float(distance) <= MAX_GENERAL_DISTANCE:
                usable.append(hit)
    def _rank(hit: dict[str, Any]):
        text = (hit.get("text") or "").lower()
        if field_name == "statement":
            return (0 if "capital gain" in text else 1, hit.get("distance") or 99.0)
        if field_name == "riskometer":
            clean = "rated" in text and "%" not in text
            return (0 if clean else 1, hit.get("distance") or 99.0)
        value_patterns = {
            "expense_ratio": r"%|\d",
            "exit_load": r"%|redeem|within|day|year",
            "min_sip": r"₹|rs\.?\s*\d|\d",
            "lock_in": r"\d|year",
            "benchmark": r"index|nifty|sensex|total\s+return|\d",
        }
        if field_name in value_patterns:
            has_value = bool(re.search(value_patterns[field_name], text))
            is_definition = any(
                phrase in text
                for phrase in ("a fee payable", "is a fee", "refers to", "is defined as")
            )
            return (0 if has_value and not is_definition else 1, hit.get("distance") or 99.0)
        exact_fact = bool(
            field_name and hit.get("is_fact") and (hit.get("section") or "") == field_name
        )
        distance = hit.get("distance")
        return (0 if exact_fact else 1, distance if distance is not None else 99.0)

    usable.sort(key=_rank)
    return usable


def _best_official_url(config: dict, question: str, hits: list[dict[str, Any]]) -> str:
    field_name = detect_field(question)
    entity_id = detect_entity(question, config)

    if field_name == "statement":
        for source in config.get("sources") or []:
            if source.get("id") == "groww-capital-gain-report" and source.get("url"):
                return source["url"]

    url = scheme_url(config, entity_id)
    if url:
        return url
    if field_name in {"returns", "benchmark"}:
        return FACTSHEET_LINK
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
    body = _clean_answer(text)
    if not body:
        body = "The indexed official pages do not contain this fact."
    return f"{body}\n\nSource: {citation_url}\nLast updated from sources: {last_updated}"


def _write_artifact(payload: dict[str, Any]) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / f"{payload['query_id']}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_client(config: dict) -> LLMClient:
    load_dotenv(ROOT / ".env")
    llm = config.get("llm") or {}
    provider = str(llm.get("provider") or "groq").lower()
    if provider == "groq":
        return GroqClient(os.getenv("GROQ_API_KEY"), llm.get("model") or os.getenv("GROQ_MODEL"))
    return _StubClient(provider)


def refusal_payload(
    config: dict,
    question: str,
    query_id: str,
    reason: str,
    message: str,
    url: str,
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "query_id": query_id,
        "query": question,
        "mode": "refuse",
        "intent": reason,
        "answer_text": message,
        "citation_url": url,
        "last_updated": (retrieval or {}).get("retrieved_at") or _utc_now(),
        "field": detect_field(question),
        "chunks_used": [],
        "model": None,
        "error": None,
        "generated_at": _utc_now(),
    }
    _write_artifact(payload)
    return payload


def generate_answer(
    config: dict,
    question: str,
    retrieval: dict[str, Any],
    query_id: str,
) -> dict[str, Any]:
    hits = list(retrieval.get("hits") or [])
    usable = select_usable_hits(question, hits)

    if not usable:
        url = _best_official_url(config, question, hits)
        return refusal_payload(
            config,
            question,
            query_id,
            reason="not_in_sources",
            message=(
                "That fact is not in the indexed official pages, so I won't guess. "
                f"Please verify it here: {url}."
            ),
            url=url,
            retrieval=retrieval,
        )

    used = usable[:MAX_CONTEXT_CHUNKS]
    if detect_field(question) == "statement":
        citation_url = _best_official_url(config, question, hits)
    else:
        citation_url = used[0].get("source_url") or _best_official_url(config, question, hits)
    last_updated = _max_fetched_at(used)

    client = _build_client(config)
    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved official chunks (the only allowed evidence):\n{_build_context(used)}"
    )
    result = client.generate(_system_prompt(), user_prompt, used)

    if result.error:
        payload = {
            "query_id": query_id,
            "query": question,
            "mode": "error",
            "intent": "fact",
            "field": detect_field(question),
            "answer_text": "",
            "citation_url": citation_url,
            "last_updated": last_updated,
            "chunks_used": [hit.get("chunk_id") for hit in used],
            "model": result.model,
            "error": result.error,
            "generated_at": _utc_now(),
        }
        _write_artifact(payload)
        return payload

    answer_text = _finalize_answer(result.answer_text, citation_url, last_updated)
    payload = {
        "query_id": query_id,
        "query": question,
        "mode": "answer",
        "intent": "fact",
        "field": detect_field(question),
        "answer_text": answer_text,
        "citation_url": citation_url,
        "last_updated": last_updated,
        "chunks_used": [hit.get("chunk_id") for hit in used],
        "model": result.model,
        "error": None,
        "generated_at": _utc_now(),
    }
    _write_artifact(payload)
    return payload
