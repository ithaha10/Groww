"""Embed chunks with the shared MiniLM model.

Reads ``data/chunks/chunks.jsonl`` and writes:

* ``data/embeddings/meta.jsonl``  — one row per chunk, aligned to the vectors
* ``data/embeddings/vectors.npy`` — float32 matrix (rows in ``chunk_id`` order)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.config import ROOT
from src.embedder import embed_texts

CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.jsonl"
META_PATH = ROOT / "data" / "embeddings" / "meta.jsonl"
VECTORS_PATH = ROOT / "data" / "embeddings" / "vectors.npy"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def embed_chunks(config: dict) -> Path:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {CHUNKS_PATH}. Run the chunk phase first: "
            "python -m src.ingest.run --phase chunk"
        )

    chunks = [
        json.loads(line)
        for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    model_name = (config.get("embedding") or {}).get(
        "model", "sentence-transformers/all-MiniLM-L6-v2"
    )

    if not chunks:
        META_PATH.write_text("", encoding="utf-8")
        np.save(VECTORS_PATH, np.zeros((0, 0), dtype=np.float32))
        print("embed: no chunks to embed")
        return META_PATH

    texts = [chunk.get("text") or "" for chunk in chunks]
    vectors = embed_texts(model_name, texts)
    vectors = np.asarray(vectors, dtype=np.float32)

    if vectors.shape[0] != len(chunks):
        raise RuntimeError(
            f"Embedding count {vectors.shape[0]} does not match chunk count {len(chunks)}"
        )

    np.save(VECTORS_PATH, vectors)

    rows = []
    for chunk, vector in zip(chunks, vectors):
        rows.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "doc_id": chunk.get("doc_id"),
                "entity_id": chunk.get("entity_id"),
                "source_url": chunk.get("source_url"),
                "section": chunk.get("section"),
                "text": chunk.get("text"),
                "fetched_at": chunk.get("fetched_at"),
                "is_fact": bool(chunk.get("is_fact")),
                "dim": int(vector.shape[0]),
            }
        )
    META_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(
        f"embed: {len(rows)} vectors (dim {vectors.shape[1]}) with model {model_name} -> "
        f"{META_PATH.relative_to(ROOT).as_posix()}"
    )
    return META_PATH
