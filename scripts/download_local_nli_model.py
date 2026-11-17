"""Explicitly download the quantized multilingual NLI model for offline use."""
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

from local_nli_verifier import MODEL_ID


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        default="models/mdeberta-v3-base-mnli-xnli",
        help="Local model directory (default: models/mdeberta-v3-base-mnli-xnli)",
    )
    args = parser.parse_args()
    destination = Path(args.destination).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=str(destination),
        allow_patterns=[
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "added_tokens.json",
            "spm.model",
            "onnx/model_quantized.onnx",
        ],
    )
    print(f"Downloaded quantized NLI model to {destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
