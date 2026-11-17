"""Explicitly build the local embedding index for one memory scope."""
from __future__ import annotations

import argparse
import json

import memory_embeddings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, help="Exact owner scope to index")
    parser.add_argument("--max-records", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=2)
    args = parser.parse_args()

    client = memory_embeddings.embedding_client_from_environment()
    if client is None:
        parser.error(
            "Local embeddings are disabled. Set ORACLE_MEMORY_EMBEDDINGS_ENABLED=1 "
            "and configure the Ollama embedding model first."
        )
    result = memory_embeddings.index_memory_scope(
        args.scope,
        client=client,
        max_records=args.max_records,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"completed", "up_to_date"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
