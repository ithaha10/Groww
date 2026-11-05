"""Structure-aware recursive chunking.

Reads ``data/raw/documents.jsonl`` (never re-fetches HTML) and writes
``data/chunks/chunks.jsonl``.

The loader flattens each page to one line per text node, so structure is
recovered heuristically:

* labelled fact rows (expense ratio, exit load, min SIP, lock-in, riskometer,
  benchmark) become **atomic** chunks so a single value never splits, and
* the remaining prose is grouped under detected headings and split with a
  recursive character splitter using ``chunk_size`` / ``chunk_overlap``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import ROOT

DOCUMENTS_PATH = ROOT / "data" / "raw" / "documents.jsonl"
CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.jsonl"
CHUNK_REPORT_PATH = ROOT / "data" / "chunks" / "chunk_report.json"

FACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("expense_ratio", re.compile(r"\bexpense\s*ratio\b|\btotal\s+expense\s+ratio\b", re.I)),
    ("exit_load", re.compile(r"\bexit\s*load\b", re.I)),
    ("min_sip", re.compile(r"\b(min(?:imum)?)[\s.]*(sip|investment)\b|\bsip\s+amount\b", re.I)),
    ("lock_in", re.compile(r"\block[\s-]?in\b", re.I)),
    (
        "riskometer",
        re.compile(
            r"\briskometer\b|\brisk\s+level\b|\brated\b.{0,25}\brisk\b|"
            r"\b(?:very\s+)?(?:high|moderate|low)\s+risk\b",
            re.I,
        ),
    ),
    ("benchmark", re.compile(r"\bbenchmark\b|\btrack(?:s|ing)?\s+(?:the\s+)?index\b", re.I)),
]

FACT_KEYS = {key for key, _ in FACT_PATTERNS}
FACT_MAX_LEN = 240
FACT_CONTINUATION_MAX = 220

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_RE = re.compile(r"\s+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fact_section(line: str) -> str | None:
    if not line or len(line) > FACT_MAX_LEN:
        return None
    for key, pattern in FACT_PATTERNS:
        if pattern.search(line):
            return key
    return None


def _looks_like_heading(line: str) -> bool:
    if not (2 <= len(line) <= 90):
        return False
    if _fact_section(line):
        return False
    if line.endswith((".", "!", ";")):
        return False
    words = line.split()
    if len(words) > 12 or not words:
        return False
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    if line.endswith("?"):
        return True
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio > 0.65:
        return True
    capitalized = sum(1 for w in words if w[:1].isupper())
    return capitalized >= max(2, int(len(words) * 0.6))


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]


def _hard_split(text: str, size: int, overlap: int) -> list[str]:
    stride = max(1, size - overlap)
    return [text[i : i + size] for i in range(0, len(text), stride) if text[i : i + size].strip()]


def _recursive_split(text: str, size: int, overlap: int) -> list[str]:
    text = WHITESPACE_RE.sub(" ", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    current = ""
    for sentence in _split_sentences(text):
        if len(sentence) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(sentence, size, overlap))
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= size:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail} {sentence}".strip() if tail else sentence
    if current:
        chunks.append(current)

    cleaned = [c.strip() for c in chunks if c.strip()]
    return cleaned if cleaned else _hard_split(text, size, overlap)


def _looks_like_value(line: str) -> bool:
    return bool(
        re.search(r"\d|%|₹|\bnifty\b|\bsensex\b|\bbse\b|\bnse\b|\btotal\s+return\b", line, re.I)
    )


def _explode_line(line: str) -> list[str]:
    """Split long multi-fact lines so each fact can stay atomic."""
    labels = {key for key, pattern in FACT_PATTERNS if pattern.search(line)}
    if not labels:
        return [line]
    if len(line) <= 120 and len(labels) < 2:
        return [line]
    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(line) if part.strip()]
    return parts or [line]


def _collect_fact_chunks(lines: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Pull fact rows out of ``lines`` and return (facts, remaining_lines)."""
    expanded: list[str] = []
    for line in lines:
        expanded.extend(_explode_line(line))

    facts: list[tuple[str, str]] = []
    remaining: list[str] = []
    i = 0
    lines = expanded
    while i < len(lines):
        line = lines[i]
        section = _fact_section(line)
        if not section:
            remaining.append(line)
            i += 1
            continue

        parts = [line]
        label_is_short = len(line) <= 80 and not re.search(r"\d", line)
        consumed = 1
        if label_is_short and i + 1 < len(lines):
            nxt = lines[i + 1]
            if not _fact_section(nxt) and (
                not _looks_like_heading(nxt) or _looks_like_value(nxt)
            ):
                parts.append(nxt)
                consumed = 2
                while (
                    consumed < 3
                    and i + consumed < len(lines)
                    and len(" ".join(parts)) < FACT_CONTINUATION_MAX
                ):
                    follow = lines[i + consumed]
                    if _fact_section(follow):
                        break
                    if _looks_like_heading(follow) and not _looks_like_value(follow):
                        break
                    parts.append(follow)
                    consumed += 1
        facts.append((section, " ".join(parts).strip()))
        i += consumed
    return facts, remaining


def _sectioned_prose(lines: list[str], fallback: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = fallback
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            sections.append((current_heading, current))
            current = []

    for line in lines:
        if _looks_like_heading(line):
            flush()
            current_heading = line
        else:
            current.append(line)
    flush()
    return [(heading, WHITESPACE_RE.sub(" ", " ".join(body)).strip()) for heading, body in sections]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:60] or "chunk"


def chunk_document(doc: dict[str, Any], chunking: dict[str, Any]) -> list[dict[str, Any]]:
    size = int(chunking.get("chunk_size") or 512)
    overlap = int(chunking.get("chunk_overlap") or 64)
    min_chars = int(chunking.get("min_chunk_chars") or 40)
    overlap = min(overlap, max(0, size - 1))

    title = (doc.get("title") or "").strip()
    text = doc.get("text") or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    facts, prose_lines = _collect_fact_chunks(lines)
    blocks: list[tuple[str, str, bool]] = []
    for section, fact_text in facts:
        blocks.append((section, fact_text, True))
    for heading, body in _sectioned_prose(prose_lines, title or "general"):
        for piece in _recursive_split(body, size, overlap):
            blocks.append((heading or title or "general", piece, False))

    chunks: list[dict[str, Any]] = []
    for index, (section, chunk_text, is_fact) in enumerate(blocks, start=1):
        if len(chunk_text) < min_chars and not is_fact:
            continue
        if not chunk_text.strip():
            continue
        section_name = section if is_fact or not title else section
        chunks.append(
            {
                "chunk_id": f"{doc.get('doc_id')}::{_slug(section_name)}::{index:04d}",
                "doc_id": doc.get("doc_id"),
                "entity_id": doc.get("entity_id"),
                "source_url": doc.get("url"),
                "section": section_name,
                "text": chunk_text,
                "fetched_at": doc.get("fetched_at"),
                "is_fact": is_fact,
            }
        )
    return chunks


def chunk_all(config: dict) -> Path:
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DOCUMENTS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {DOCUMENTS_PATH}. Run the load phase first: "
            "python -m src.ingest.run --phase load"
        )

    chunking = config.get("chunking") or {}
    documents = [
        json.loads(line)
        for line in DOCUMENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    all_chunks: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    per_doc: list[dict[str, Any]] = []

    for doc in documents:
        produced = chunk_document(doc, chunking)
        for chunk in produced:
            base = chunk["chunk_id"]
            count = seen.get(base, 0)
            seen[base] = count + 1
            if count:
                chunk["chunk_id"] = f"{base}-{count + 1}"
            all_chunks.append(chunk)
        per_doc.append(
            {
                "doc_id": doc.get("doc_id"),
                "title": doc.get("title"),
                "chunks": len(produced),
                "fact_chunks": sum(1 for c in produced if c["is_fact"]),
            }
        )

    CHUNKS_PATH.write_text(
        "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in all_chunks),
        encoding="utf-8",
    )
    report = {
        "chunked_at": _utc_now(),
        "strategy": chunking.get("strategy", "structure_recursive"),
        "chunk_size": chunking.get("chunk_size"),
        "chunk_overlap": chunking.get("chunk_overlap"),
        "documents": per_doc,
        "total_chunks": len(all_chunks),
    }
    CHUNK_REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"chunk: {len(all_chunks)} chunks from {len(documents)} documents -> {CHUNKS_PATH.relative_to(ROOT).as_posix()}")
    return CHUNKS_PATH
