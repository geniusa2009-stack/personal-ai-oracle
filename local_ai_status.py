"""Read-only local configuration inventory. Never loads models or probes a network."""
import os
from pathlib import Path

import local_nli_verifier as nli
import memory_embeddings


def snapshot() -> dict:
    try:
        client = memory_embeddings.embedding_client_from_environment()
        embedding = {'configured': client is not None, 'provider': type(client).__name__ if client else None, 'model': client.model_name if client else None}
    except memory_embeddings.EmbeddingError:
        embedding = {'configured': False, 'error': 'Invalid embedding configuration'}
    directory = os.environ.get('ORACLE_NLI_MODEL_DIR', '').strip()
    files_present = bool(directory) and all((Path(directory).expanduser() / name).is_file() for name in ('config.json', 'onnx/model_quantized.onnx'))
    try:
        threshold = nli._threshold()
    except nli.LocalNLIError:
        threshold = None
    return {'embedding': {**embedding, 'installed': 'unknown', 'operational': 'unverified'}, 'nli': {'configured': os.environ.get('ORACLE_SEMANTIC_VERIFIER') == 'local_nli', 'required_weight_files_present': files_present, 'tokenizer_and_runtime': 'unverified', 'threshold': threshold, 'operational': 'unverified'}, 'real_model_tested': False, 'verified_on_target_mac': False, 'indexing_status': 'not tracked', 'last_verification': 'not tracked', 'resource_failures': 'not tracked'}
