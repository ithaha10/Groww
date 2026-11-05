from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

DATA_DIRS = [
    ROOT / "data" / "raw" / "html",
    ROOT / "data" / "raw",
    ROOT / "data" / "chunks",
    ROOT / "data" / "embeddings",
    ROOT / "data" / "chroma",
    ROOT / "data" / "retrieved",
    ROOT / "data" / "generated",
]


def ensure_data_dirs() -> None:
    for path in DATA_DIRS:
        path.mkdir(parents=True, exist_ok=True)


def get_config() -> dict:
    load_dotenv(ROOT / ".env")
    config_path = ROOT / "config.yaml"
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    llm = cfg.setdefault("llm", {})
    if llm.get("provider") == "groq":
        llm["model"] = os.getenv("GROQ_MODEL", llm.get("model") or "")
    return cfg
