"""Embed the question, query the shared Chroma collection, persist hits."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import ROOT
from src.embedder import embed_texts
from src.query.guardrails import detect_field

RETRIEVED_DIR = ROOT / "data" / "retrieved"

VALUE_PATTERNS = {
    "expense_ratio": r"%|\d",
    "exit_load": r"%|redeem|within|day|year",
    "min_sip": r"₹|rs\.?\s*\d|\d",
    "lock_in": r"\d|year",
    "benchmark": r"index|nifty|sensex|total\s+return|\d",
}
DEFINITION_PHRASES = ("a fee payable", "is a fee", "refers to", "is defined as")

SCHEME_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("hdfc-large-cap-direct-growth", ("large cap", "large-cap")),
    ("hdfc-flexi-cap-direct-growth", ("flexi cap", "flexi-cap", "equity fund")),
    ("hdfc-elss-tax-saver-direct-growth", ("elss", "tax saver", "tax-saver")),
    ("hdfc-mid-cap-direct-growth", ("mid cap", "mid-cap")),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_query_id() -> str:
    return uuid.uuid4().hex[:12]


def configured_entity_ids(config: dict) -> set[str]:
    return {
        s.get("entity_id")
        for s in (config.get("sources") or [])
        if s.get("entity_type") == "scheme" and s.get("entity_id")
    }


def detect_entity(question: str, config: dict) -> str | None:
    text = (question or "").lower()
    available = configured_entity_ids(config)
    for entity_id, aliases in SCHEME_ALIASES:
        if entity_id in available and any(alias in text for alias in aliases):
            return entity_id
    return None


def scheme_url(config: dict, entity_id: str | None) -> str | None:
    if not entity_id:
        return None
    for source in config.get("sources") or []:
        if source.get("entity_id") == entity_id and source.get("url"):
            return source["url"]
    return None


def _collection(config: dict):
    import chromadb

    chroma_cfg = config.get("chroma") or {}
    persist_dir = ROOT / str(chroma_cfg.get("persist_dir", "data/chroma"))
    name = str(chroma_cfg.get("collection", "groww_mf_faq"))
    if not persist_dir.exists():
        raise RuntimeError(
            "Chroma store not found. Run ingestion first: python -m src.ingest.run --phase all"
        )
    client = chromadb.PersistentClient(path=str(persist_dir))
    try:
        collection = client.get_collection(name)
    except Exception as exc:
        raise RuntimeError(
            "Chroma collection is empty. Run ingestion first: "
            "python -m src.ingest.run --phase all"
        ) from exc
    if collection.count() == 0:
        raise RuntimeError(
            "Chroma collection is empty. Run ingestion first: "
            "python -m src.ingest.run --phase all"
        )
    return collection


def _fact_priority(field_name: str, text: str) -> int:
    text = (text or "").lower()
    if field_name == "riskometer":
        return 0 if ("rated" in text and "%" not in text) else 1
    pattern = VALUE_PATTERNS.get(field_name)
    has_value = bool(re.search(pattern, text)) if pattern else False
    is_definition = any(phrase in text for phrase in DEFINITION_PHRASES)
    return 0 if has_value and not is_definition else 1


def _write_artifact(artifact: dict[str, Any]) -> None:
    RETRIEVED_DIR.mkdir(parents=True, exist_ok=True)
    path = RETRIEVED_DIR / f"{artifact['query_id']}.json"
    path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")


def retrieve(
    config: dict,
    question: str,
    query_id: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    query_id = query_id or new_query_id()
    top_k = int((config.get("retrieval") or {}).get("top_k") or 5)
    model_name = (config.get("embedding") or {}).get(
        "model", "sentence-transformers/all-MiniLM-L6-v2"
    )
    entity_id = detect_entity(question, config)

    collection = _collection(config)
    embedding = embed_texts(model_name, [question])[0].tolist()
    field_name = detect_field(question)

    def _query(where, n_results: int = top_k):
        return collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def _hits_from(result) -> list[dict[str, Any]]:
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        out: list[dict[str, Any]] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] or {}
            distance = float(distances[index]) if index < len(distances) else None
            out.append(
                {
                    "chunk_id": chunk_id,
                    "distance": distance,
                    "score": None if distance is None else round(1.0 - distance, 4),
                    "doc_id": metadata.get("doc_id"),
                    "entity_id": metadata.get("entity_id"),
                    "source_url": metadata.get("source_url"),
                    "section": metadata.get("section"),
                    "text": documents[index] if index < len(documents) else "",
                    "fetched_at": metadata.get("fetched_at"),
                    "is_fact": bool(metadata.get("is_fact")),
                }
            )
        return out

    result = _query({"entity_id": entity_id} if entity_id else None)
    if entity_id and not (result.get("ids") and result["ids"][0]):
        result = _query(None)

    hits = _hits_from(result)

    # Boost the exact labelled fact rows for the asked field + scheme. MiniLM
    # otherwise tends to rank long prose/definitions above a terse atomic row.
    if entity_id and field_name and field_name != "statement":
        fact_result = _query(
            {"$and": [{"entity_id": {"$eq": entity_id}}, {"section": {"$eq": field_name}}]},
            n_results=10,
        )
        fact_hits = _hits_from(fact_result)
        fact_hits.sort(
            key=lambda h: (
                _fact_priority(field_name, h.get("text") or ""),
                h.get("distance") if h.get("distance") is not None else 99.0,
            )
        )
        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for hit in fact_hits[:3] + hits:
            if hit["chunk_id"] in seen_ids:
                continue
            seen_ids.add(hit["chunk_id"])
            merged.append(hit)
        hits = merged[:top_k]

    artifact = {
        "query_id": query_id,
        "query": question,
        "top_k": top_k,
        "entity_filter": entity_id,
        "field_filter": field_name,
        "embedding_model": model_name,
        "retrieved_at": _utc_now(),
        "hits": hits,
    }
    if persist:
        _write_artifact(artifact)
    return artifact
