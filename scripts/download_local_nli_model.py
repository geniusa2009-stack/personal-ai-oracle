"""Explicitly download the quantized multilingual NLI model for offline use."""
from __future__ import annotations

import argparse
from pathlib import Path

import hashlib
import json

from local_nli_verifier import MODEL_ID


def verify_download(destination: Path, manifest: dict) -> None:
    """Validate pinned artifacts before writing provenance; no network calls."""
    hashes = {}
    for name, expected in manifest['files'].items():
        path = destination / name
        if not path.is_file() or path.stat().st_size != expected['bytes']:
            raise RuntimeError('Downloaded model file size mismatch: ' + name)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        hashes[name] = digest.hexdigest()
        if expected['sha256'] and hashes[name] != expected['sha256']:
            raise RuntimeError('Downloaded model checksum mismatch: ' + name)
    (destination / 'provenance.json').write_text(json.dumps({**manifest, 'actual_sha256': hashes}, indent=2) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination",
        default="models/mdeberta-v3-base-mnli-xnli",
        help="Local model directory (default: models/mdeberta-v3-base-mnli-xnli)",
    )
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    manifest = json.loads((Path(__file__).resolve().parents[1] / 'docs/engineering/local-nli-upstream-manifest.json').read_text())
    destination = Path(args.destination).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        revision=manifest["revision"],
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
    verify_download(destination, manifest)
    print(f"Downloaded quantized NLI model to {destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
