"""Explicit offline evaluation; never downloads weights or invokes hosted models."""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import hashlib
import os
import json
from pathlib import Path
import platform
import resource
import time

import local_nli_verifier as nli
from local_model_lifecycle import ResourceUnavailable, memory_status


def provenance():
    directory = Path(os.environ.get('ORACLE_NLI_MODEL_DIR', '.'))
    files = {}
    for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'spm.model', 'provenance.json'):
        path = directory / name
        if path.is_file():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path = directory / 'provenance.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    return {'model_id': nli.MODEL_ID, 'file_sha256': files, 'upstream_revision': manifest.get('revision', 'unknown'), 'tokenizer_revision': manifest.get('revision', 'unknown'), 'provenance_status': 'recorded manifest; integrity requires explicit downloader validation' if manifest else 'unverified'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[1] / 'tests/fixtures/local_nli_eval.json')
    parser.add_argument('--mode', choices=('cold', 'session'), default='cold')
    args = parser.parse_args()
    cases = json.loads(args.dataset.read_text(encoding='utf-8'))
    if not isinstance(cases, list) or not 1 <= len(cases) <= 48:
        parser.error('dataset must contain 1–48 cases')
    if sum(len(c['evidence']) for case in cases for c in case['claims']) > nli.MAX_PAIRS_PER_RUN:
        parser.error('evaluation batch exceeds 48 evidence pairs')
    rows = []
    pressure_before = memory_status()
    started = time.perf_counter()
    cpu_started = time.process_time()
    context = nli.evaluation_session() if args.mode == 'session' else nullcontext(nli.judge_payload)
    try:
        with context as judge:
            for case in cases:
                begin = time.perf_counter()
                cpu_begin = time.process_time()
                try:
                    result = json.loads(judge({'claims': case['claims']}))['results'][0]
                    actual, error = result['status'], None
                except (nli.LocalNLIError, ResourceUnavailable) as exc:
                    actual, error = 'UNVERIFIED', type(exc).__name__
                rows.append({'id': case['id'], 'language': case['language'], 'expected': case['expected'], 'actual': actual, 'matches': actual == case['expected'], 'seconds': time.perf_counter() - begin, 'cpu_seconds': time.process_time() - cpu_begin, 'error': error})
    except ResourceUnavailable as exc:
        print(json.dumps({'status': 'BLOCKED', 'error_category': type(exc).__name__, 'results': rows}))
        return 1
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({'mode': args.mode, 'provenance': provenance(), 'pressure_before': pressure_before, 'pressure_after': memory_status(), 'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(), 'threshold': nli._threshold(), 'model': nli.MODEL_ID, 'seconds': time.perf_counter() - started, 'cpu_seconds': time.process_time() - cpu_started, 'peak_process_rss_bytes': peak if platform.system() == 'Darwin' else peak * 1024, 'notes': 'Cold mode loads per case; session mode loads at first usable evidence and releases after the bounded batch. Peak is process-wide, not model allocation. Text entailment is not factual truth.', 'results': rows}, ensure_ascii=False, indent=2))
    return 0 if all(row['matches'] and not row['error'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
