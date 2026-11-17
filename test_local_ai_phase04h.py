import json
import subprocess
import sys
import pytest
import db
import local_ai_telemetry as telemetry
import local_model_lifecycle as lifecycle
import local_nli_verifier as nli


def test_scope_counts_and_retention(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setattr(telemetry, 'MAX_EVENTS', 2)
    for _ in range(3):
        telemetry.record('owner:a', 'indexing', 'end', 'test-model', counts={'indexed_count': 1, 'raw_text': 'private'}, error='private exception')
    assert len(telemetry.recent('owner:a', 2)) == 2
    assert telemetry.recent('owner:b', 2) == []
    assert 'private' not in json.dumps(telemetry.recent('owner:a', 2))
    with pytest.raises(ValueError):
        telemetry.recent('')


def test_pressure_blocks_work(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, 'memory_status', lambda: {'free_percent': 2})
    with pytest.raises(lifecycle.ResourceUnavailable):
        with lifecycle.workload(lock_path=str(tmp_path / 'model.lock')):
            pytest.fail('must not execute')


def test_lock_timeout_and_crash_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, 'memory_status', lambda: {'free_percent': 50})
    path = str(tmp_path / 'model.lock')
    code = 'import fcntl,os,sys,time; f=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600); fcntl.flock(f,fcntl.LOCK_EX); print("locked",flush=True); time.sleep(30)'
    child = subprocess.Popen([sys.executable, '-c', code, path], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'locked'
        with pytest.raises(lifecycle.ResourceUnavailable, match='timeout'):
            with lifecycle.workload(timeout=0.1, lock_path=path):
                pass
    finally:
        child.kill()
        child.wait()
        child.stdout.close()
    with lifecycle.workload(timeout=0.2, lock_path=path) as state:
        assert state['before']['free_percent'] == 50
    assert state['after']['free_percent'] == 50


def test_explicit_session_reuses_model_and_disposes(monkeypatch):
    monkeypatch.setattr(lifecycle, 'memory_status', lambda: {'free_percent': 50})
    calls = []
    class Model:
        def __init__(self, path):
            calls.append(path)
        def score(self, premise, hypothesis):
            return {'entailment': .99, 'neutral': .005, 'contradiction': .005}
    monkeypatch.setattr(nli, 'LocalNLIModel', Model)
    monkeypatch.setenv('ORACLE_NLI_MODEL_DIR', '/synthetic-model')
    payload = {'claims':[{'claim_id':'C1','claim':'claim','evidence':[{'source_id':'S1','excerpt':'evidence','evidence_level':'extracted_page'}]}]}
    with nli.evaluation_session() as judge:
        judge(payload)
        judge(payload)
        assert len(calls) == 1
    assert not nli._MODEL_CACHE
    nli.judge_payload(payload)
    assert len(calls) == 2


@pytest.mark.parametrize('mode,loads', [('cold', 2), ('session', 1)])
def test_runner_modes_report_predictions_cpu_and_provenance(monkeypatch, tmp_path, capsys, mode, loads):
    from scripts import evaluate_local_nli as runner
    monkeypatch.setattr(lifecycle, 'memory_status', lambda: {'free_percent': 50})
    calls = []
    class Model:
        def __init__(self, path): calls.append(path)
        def score(self, premise, hypothesis):
            return {'entailment': .99, 'neutral': .005, 'contradiction': .005}
    monkeypatch.setattr(nli, 'LocalNLIModel', Model)
    monkeypatch.setenv('ORACLE_NLI_MODEL_DIR', str(tmp_path))
    case = {'id': 'synthetic', 'language': 'en', 'expected': 'SUPPORTED', 'claims': [{'claim_id': 'C1', 'claim': 'claim', 'evidence':[{'source_id':'S1', 'excerpt':'evidence', 'evidence_level':'extracted_page'}]}]}
    dataset = tmp_path / 'cases.json'
    dataset.write_text(json.dumps([case,case]))
    monkeypatch.setattr(sys, 'argv', ['evaluate', '--mode', mode, '--dataset', str(dataset)])
    assert runner.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['mode'] == mode
    assert all(row['actual'] == 'SUPPORTED' and row['cpu_seconds'] >= 0 for row in result['results'])
    assert result['peak_process_rss_bytes'] > 0
    assert result['provenance']['model_id'] == nli.MODEL_ID
    assert len(calls) == loads
    assert not nli._MODEL_CACHE


def test_verification_persists_only_explicit_owner_metadata(monkeypatch, tmp_path):
    import semantic_verifier
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'events.db'))
    monkeypatch.setattr(semantic_verifier, '_verify_claims', lambda *a, **k: {'status': 'completed', 'results': [{'status': 'SUPPORTED', 'claim': 'private sentence'}]})
    semantic_verifier.verify_claims([], [], scope='owner:explicit')
    rows = telemetry.recent('owner:explicit')
    assert len(rows) == 2
    assert json.loads(rows[0]['counts_json']) == {'SUPPORTED': 1}
    assert 'private sentence' not in str(rows)
    assert telemetry.recent('owner:other') == []


def test_downloader_integrity_checks_without_network(tmp_path):
    import hashlib
    from scripts.download_local_nli_model import verify_download
    data = b'synthetic model, not real weights'
    path = tmp_path / 'model.onnx'
    path.write_bytes(data)
    manifest = {'revision': 'synthetic', 'files': {'model.onnx': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
    verify_download(tmp_path, manifest)
    assert json.loads((tmp_path / 'provenance.json').read_text())['revision'] == 'synthetic'
    path.write_bytes(b'x' * len(data))
    with pytest.raises(RuntimeError, match='checksum'):
        verify_download(tmp_path, manifest)
    path.write_bytes(b'x')
    with pytest.raises(RuntimeError, match='size'):
        verify_download(tmp_path, manifest)
