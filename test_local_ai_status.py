import local_ai_status


def test_status_does_not_claim_readiness_from_weight_files(monkeypatch, tmp_path):
    (tmp_path / 'onnx').mkdir()
    (tmp_path / 'config.json').write_text('{}')
    (tmp_path / 'onnx/model_quantized.onnx').touch()
    monkeypatch.setenv('ORACLE_NLI_MODEL_DIR', str(tmp_path))
    monkeypatch.setenv('ORACLE_SEMANTIC_VERIFIER', 'local_nli')
    monkeypatch.setenv('ORACLE_MEMORY_EMBEDDINGS_ENABLED', '0')
    result = local_ai_status.snapshot()
    assert result['nli']['required_weight_files_present'] is True
    assert result['nli']['operational'] == 'unverified'
    assert result['verified_on_target_mac'] is False


def test_status_redacts_invalid_configuration(monkeypatch):
    monkeypatch.setenv('ORACLE_MEMORY_EMBEDDINGS_ENABLED', '1')
    monkeypatch.setenv('ORACLE_EMBEDDING_BASE_URL', 'https://secret:password@example.org')
    monkeypatch.setenv('ORACLE_NLI_THRESHOLD', 'nan')
    result = local_ai_status.snapshot()
    assert 'password' not in str(result)
    assert result['nli']['threshold'] is None
