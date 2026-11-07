import sqlite3

import db
import model_observability


def test_model_metrics_are_scoped_and_summarized_without_prompt_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "model-metrics.db"))
    model_observability.record_event(
        scope="owner-a", provider="openai", model="gpt-test",
        route_reason="tier:deep", latency_ms=100, outcome="success",
        output_chars=250,
    )
    model_observability.record_event(
        scope="owner-a", provider="openai", model="gpt-test",
        route_reason="tier:deep", latency_ms=300, outcome="error",
        output_chars=0,
    )
    model_observability.record_event(
        scope="owner-b", provider="ollama", model="local-test",
        route_reason="default", latency_ms=10, outcome="success",
    )
    rows = model_observability.summary("owner-a")
    assert len(rows) == 1
    assert rows[0]["requests"] == 2
    assert rows[0]["success_rate"] == 0.5
    assert rows[0]["errors"] == 1
    assert rows[0]["p50_latency_ms"] == 100
    assert rows[0]["p95_latency_ms"] == 300
    assert model_observability.summary("owner-b")[0]["provider"] == "ollama"

    connection = db.get_conn()
    try:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(oracle_model_events)")
        }
        assert not {"prompt", "completion", "messages", "tool_input"} & columns
    finally:
        connection.close()


def test_model_metrics_reject_invalid_values(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "invalid-metrics.db"))
    model_observability.record_event(
        scope="owner-a", provider="test", model="test",
        route_reason="test", latency_ms=-1, outcome="success",
    )
    assert model_observability.list_events("owner-a") == []
