from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ensure_data_dirs, get_config
from src.ingest.chunk import chunk_all
from src.ingest.embed import embed_chunks
from src.ingest.load import load_all
from src.ingest.scrape import scrape_all
from src.ingest.store import store_chunks

PHASES = ("scrape", "load", "chunk", "embed", "store")


def run_phase(name: str, config: dict) -> None:
    if name == "scrape":
        scrape_all(config)
    elif name == "load":
        load_all(config)
    elif name == "chunk":
        chunk_all(config)
    elif name == "embed":
        embed_chunks(config)
    elif name == "store":
        store_chunks(config)
    else:
        raise ValueError(f"Unknown phase: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Groww MF FAQ ingestion")
    parser.add_argument(
        "--phase",
        required=True,
        choices=[*PHASES, "all"],
        help="Pipeline stage to run",
    )
    args = parser.parse_args()

    ensure_data_dirs()
    config = get_config()

    phases = PHASES if args.phase == "all" else (args.phase,)
    for name in phases:
        run_phase(name, config)


if __name__ == "__main__":
    main()
