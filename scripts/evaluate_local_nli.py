"""Explicit offline evaluation; never downloads weights or invokes hosted models."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import platform
import resource
import time

import local_nli_verifier as nli


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=Path(__file__).resolve().parents[1] / 'tests/fixtures/local_nli_eval.json')
    args = parser.parse_args()
    cases = json.loads(args.dataset.read_text(encoding='utf-8'))
    rows = []
    started = time.perf_counter()
    cpu_started = time.process_time()
    for case in cases:
        begin = time.perf_counter()
        try:
            result = json.loads(nli.judge_payload({'claims': case['claims']}))['results'][0]
            actual, error = result['status'], None
        except nli.LocalNLIError as exc:
            actual, error = 'UNVERIFIED', str(exc)
        rows.append({'id': case['id'], 'language': case['language'], 'expected': case['expected'], 'actual': actual, 'matches': actual == case['expected'], 'seconds': time.perf_counter() - begin, 'error': error})
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(), 'threshold': nli._threshold(), 'model': nli.MODEL_ID, 'seconds': time.perf_counter() - started, 'cpu_seconds': time.process_time() - cpu_started, 'peak_process_rss_bytes': peak if platform.system() == 'Darwin' else peak * 1024, 'notes': 'Includes cold load per case. Peak is process-wide, not model allocation. Text entailment is not factual truth.', 'results': rows}, ensure_ascii=False, indent=2))
    return 0 if all(row['matches'] and not row['error'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
