"""Rebuild the Chroma collection from embedded chunks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from src.config import ROOT

META_PATH = ROOT / "data" / "embeddings" / "meta.jsonl"
VECTORS_PATH = ROOT / "data" / "embeddings" / "vectors.npy"
COLLECTION_INFO_PATH = ROOT / "data" / "chroma" / "collection_info.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_metadata(row: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {}
    for key in ("doc_id", "entity_id", "source_url", "section", "fetched_at"):
        value = row.get(key)
        metadata[key] = "" if value is None else str(value)
    metadata["is_fact"] = bool(row.get("is_fact"))
    return metadata


def store_chunks(config: dict) -> Path:
    import chromadb

    if not META_PATH.exists() or not VECTORS_PATH.exists():
        raise FileNotFoundError(
            f"Missing embeddings in {META_PATH.parent}. Run the embed phase first: "
            "python -m src.ingest.run --phase embed"
        )

    chroma_cfg = config.get("chroma") or {}
    persist_dir = ROOT / str(chroma_cfg.get("persist_dir", "data/chroma"))
    collection_name = str(chroma_cfg.get("collection", "groww_mf_faq"))
    persist_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        json.loads(line)
        for line in META_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    vectors = np.load(VECTORS_PATH)
    if vectors.shape[0] != len(rows):
        raise RuntimeError(
            f"Vector count {vectors.shape[0]} does not match metadata count {len(rows)}"
        )

    client = chromadb.PersistentClient(path=str(persist_dir))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    if rows:
        collection.add(
            ids=[row["chunk_id"] for row in rows],
            embeddings=vectors.astype(np.float32).tolist(),
            documents=[row.get("text") or "" for row in rows],
            metadatas=[_clean_metadata(row) for row in rows],
        )

    info = {
        "collection": collection_name,
        "count": collection.count(),
        "embedding_model": (config.get("embedding") or {}).get("model"),
        "persist_dir": str(persist_dir.relative_to(ROOT).as_posix()),
        "updated_at": _utc_now(),
    }
    COLLECTION_INFO_PATH.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(
        f"store: {info['count']} vectors in collection '{collection_name}' -> "
        f"{persist_dir.relative_to(ROOT).as_posix()}"
    )
    return COLLECTION_INFO_PATH
