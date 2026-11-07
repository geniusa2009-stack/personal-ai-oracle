import math

import pytest

import ai_core
import db
import hybrid_memory
import memory
import memory_embeddings
import memory_layers


def _use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "hybrid-memory.db"))


class FakeEmbeddingClient:
    model_name = "test-embedding-v1"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            normalized = text.casefold()
            if "galaxy" in normalized or "astronomy" in normalized or "space" in normalized:
                vectors.append([1.0, 0.0, 0.0])
            elif "ocean" in normalized or "marine" in normalized:
                vectors.append([0.0, 1.0, 0.0])
            elif "workflow" in normalized or "procedure" in normalized:
                vectors.append([0.0, 0.0, 1.0])
            elif "unrelated" in normalized or "music" in normalized:
                vectors.append([0.0, 0.0, 1.0])
            else:
                vectors.append([0.5, 0.5, 0.0])
        return vectors


def test_cosine_similarity_and_vector_validation():
    assert memory_embeddings.cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)
    assert memory_embeddings.cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
    assert memory_embeddings.cosine_similarity([1, 0, 0], [-1, 0, 0]) == pytest.approx(-1.0)
    assert memory_embeddings.cosine_similarity([1, 0], [0, 1, 2]) == 0.0

    for invalid in ([0, 0], [1], [float("nan"), 1], [float("inf"), 1], [True, 1], "not a vector"):
        with pytest.raises(memory_embeddings.EmbeddingError):
            memory_embeddings._validate_vector(invalid)


def test_embedding_configuration_is_opt_in(monkeypatch):
    monkeypatch.delenv("ORACLE_MEMORY_EMBEDDINGS_ENABLED", raising=False)
    monkeypatch.delenv("ORACLE_EMBEDDING_MODEL", raising=False)

    assert memory_embeddings.embedding_client_from_environment() is None


def test_index_scope_is_idempotent_and_does_not_duplicate_raw_memory(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    memory.write_memory(
        "Studies galaxy clusters and stellar systems",
        "fact",
        "owner:one",
        "manual",
    )
    client = FakeEmbeddingClient()

    first = memory_embeddings.index_memory_scope(
        "owner:one", client=client
    )
    second = memory_embeddings.index_memory_scope(
        "owner:one", client=client
    )

    assert first["status"] == "completed"
    assert first["indexed_count"] == 1
    assert second["status"] == "up_to_date"
    assert second["skipped_count"] == 1
    assert len(client.calls) == 1

    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT scope, memory_type, record_id, embedding_model, content_hash, vector_json "
            "FROM memory_embeddings"
        ).fetchone()
        assert row["scope"] == "owner:one"
        assert row["memory_type"] == "fact"
        assert row["embedding_model"] == client.model_name
        assert len(row["content_hash"]) == 64
        assert "Studies galaxy clusters" not in row["vector_json"]
    finally:
        conn.close()


def test_vector_search_can_retrieve_semantically_related_but_lexically_different_memory(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    record = memory.write_memory(
        "Studies galaxy clusters and stellar systems",
        "fact",
        "owner:one",
        "manual",
    )
    client = FakeEmbeddingClient()
    memory_embeddings.index_memory_scope("owner:one", client=client)

    matches = memory_embeddings.retrieve_vector_matches(
        "owner:one", "astronomy space", client=client
    )

    assert len(matches) == 1
    assert matches[0].record.id == record.id
    assert matches[0].similarity == pytest.approx(1.0)


def test_vector_retrieval_is_scope_isolated(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    own = memory.write_memory(
        "Studies galaxy clusters", "fact", "owner:one", "manual"
    )
    memory.write_memory(
        "Studies galaxy clusters", "fact", "owner:two", "manual"
    )
    client = FakeEmbeddingClient()
    memory_embeddings.index_memory_scope("owner:one", client=client)
    memory_embeddings.index_memory_scope("owner:two", client=client)

    matches = memory_embeddings.retrieve_vector_matches(
        "owner:one", "astronomy", client=client
    )

    assert [item.record.id for item in matches] == [own.id]
    assert all(item.record.scope == "owner:one" for item in matches)


def test_stale_vectors_are_ignored_after_source_record_changes(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    record = memory.write_memory(
        "Studies galaxy clusters", "fact", "owner:one", "manual"
    )
    client = FakeEmbeddingClient()
    memory_embeddings.index_memory_scope("owner:one", client=client)

    conn = db.get_conn()
    try:
        conn.execute(
            "UPDATE memories SET content = ?, normalized_content = ? WHERE id = ? AND scope = ?",
            ("Studies ocean currents", "Studies ocean currents", record.id, "owner:one"),
        )
        conn.commit()
    finally:
        conn.close()

    matches = memory_embeddings.retrieve_vector_matches(
        "owner:one", "astronomy", client=client
    )
    assert matches == []


def test_hybrid_retrieval_uses_vector_rank_and_keeps_lexical_results(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    lexical = memory.write_memory(
        "astronomy notes", "fact", "owner:one", "manual"
    )
    semantic = memory.write_memory(
        "Studies galaxy clusters and stellar systems", "fact", "owner:one", "manual"
    )
    client = FakeEmbeddingClient()
    memory_embeddings.index_memory_scope("owner:one", client=client)

    context = hybrid_memory.retrieve_memory_context(
        "owner:one", "astronomy", client=client
    )

    assert context.retrieval_mode == "hybrid"
    assert context.semantic_match_count == 2
    assert {item.id for item in context.memories} == {lexical.id, semantic.id}
    assert context.embedding_model == client.model_name


def test_hybrid_retrieval_falls_back_to_lexical_on_provider_error(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    lexical = memory.write_memory(
        "Builds an Oracle project", "fact", "owner:one", "manual"
    )

    class BrokenClient:
        model_name = "broken-model"

        def embed(self, _texts):
            raise RuntimeError("provider unavailable")

    context = hybrid_memory.retrieve_memory_context(
        "owner:one", "Oracle project", client=BrokenClient()
    )

    assert context.retrieval_mode == "lexical_fallback"
    assert [item.id for item in context.memories] == [lexical.id]
    assert context.warning_code == "RuntimeError"


def test_hybrid_retrieval_does_not_auto_index_or_call_embeddings_by_default(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    lexical = memory.write_memory(
        "Builds an Oracle project", "fact", "owner:one", "manual"
    )
    client = FakeEmbeddingClient()

    context = hybrid_memory.retrieve_memory_context(
        "owner:one", "Oracle project", client=client, auto_index=False
    )

    assert context.retrieval_mode == "lexical_fallback"
    assert [item.id for item in context.memories] == [lexical.id]
    assert client.calls == []


def test_ai_core_uses_hybrid_retrieval_without_leaking_other_scopes(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    own = memory.write_memory(
        "Studies galaxy clusters and stellar systems", "fact", "owner:one", "manual"
    )
    private = memory.write_memory(
        "Studies galaxy clusters privately", "fact", "owner:two", "manual"
    )
    client = FakeEmbeddingClient()
    memory_embeddings.index_memory_scope("owner:one", client=client)
    memory_embeddings.index_memory_scope("owner:two", client=client)
    monkeypatch.setattr(
        memory_embeddings,
        "embedding_client_from_environment",
        lambda: client,
    )

    messages = [
        {"role": "user", "content": "Tell me about astronomy space"},
    ]
    enriched = ai_core._messages_with_memory(messages, "owner:one")
    content = enriched[0]["content"]

    assert "Studies galaxy clusters and stellar systems" in content
    assert "Studies galaxy clusters privately" not in content
    assert "<personal_memory>" in content
    assert private.id != own.id


def test_vector_search_filters_low_similarity_matches(monkeypatch, tmp_path):
    _use_test_database(monkeypatch, tmp_path)
    record = memory.write_memory(
        "Studies galaxy clusters", "fact", "owner:one", "manual"
    )
    client = FakeEmbeddingClient()
    memory_embeddings.index_memory_scope("owner:one", client=client)

    matches = memory_embeddings.retrieve_vector_matches(
        "owner:one", "unrelated music", client=client
    )

    assert matches == []
    with pytest.raises(memory_embeddings.EmbeddingError):
        memory_embeddings.retrieve_vector_matches(
            "owner:one", "astronomy", client=client, min_similarity=2.0
        )


def test_openai_compatible_embedding_client_sorts_and_validates_response_indexes(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    captured = {}

    def post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse({
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        })

    monkeypatch.setattr(memory_embeddings.requests, "post", post)
    client = memory_embeddings.OpenAICompatibleEmbeddingClient(
        base_url="http://127.0.0.1:11434/v1",
        model_name="nomic-embed-text",
        api_key="local-token",
    )
    vectors = client.embed(["first", "second"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert captured["url"] == "http://127.0.0.1:11434/v1/embeddings"
    assert captured["json"] == {"model": "nomic-embed-text", "input": ["first", "second"]}
    assert captured["headers"]["Authorization"] == "Bearer local-token"
    assert captured["timeout"] == memory_embeddings.EMBEDDING_TIMEOUT_SECONDS

    def duplicate_index_post(*args, **kwargs):
        return FakeResponse({
            "data": [
                {"index": 0, "embedding": [1.0, 0.0]},
                {"index": 0, "embedding": [0.0, 1.0]},
            ]
        })

    monkeypatch.setattr(memory_embeddings.requests, "post", duplicate_index_post)
    with pytest.raises(memory_embeddings.EmbeddingError):
        client.embed(["first", "second"])


def test_embedding_provider_failure_is_normalized_without_leaking_response_text(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise memory_embeddings.requests.HTTPError("private provider response body")

    monkeypatch.setattr(
        memory_embeddings.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )
    client = memory_embeddings.OpenAICompatibleEmbeddingClient(
        base_url="https://embeddings.example/v1",
        model_name="embedding-model",
        api_key="secret-token",
    )

    with pytest.raises(memory_embeddings.EmbeddingError) as exc:
        client.embed(["text"])

    assert "private provider response body" not in str(exc.value)
    assert "secret-token" not in str(exc.value)
