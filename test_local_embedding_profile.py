import memory_embeddings


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "embeddings": [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        }


def test_ollama_local_embedding_profile_uses_embeddinggemma_270m(monkeypatch):
    monkeypatch.setenv("ORACLE_MEMORY_EMBEDDINGS_ENABLED", "1")
    monkeypatch.setenv("ORACLE_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("ORACLE_EMBEDDING_MODEL", "embeddinggemma-2:270m")
    monkeypatch.delenv("ORACLE_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    client = memory_embeddings.embedding_client_from_environment()

    assert client is not None
    assert client.model_name == "embeddinggemma-2:270m"
    assert isinstance(client, memory_embeddings.OllamaEmbeddingClient)
    assert client.url == "http://127.0.0.1:11434/api/embed"
    assert client.keep_alive == "0"


def test_ollama_embedding_adapter_validates_and_orders_local_vectors(monkeypatch):
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr(memory_embeddings.requests, "post", fake_post)
    client = memory_embeddings.OllamaEmbeddingClient(
        base_url="http://127.0.0.1:11434",
        model_name="embeddinggemma-2:270m",
    )

    vectors = client.embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert calls[0][0] == "http://127.0.0.1:11434/api/embed"
    assert calls[0][1] == {
        "model": "embeddinggemma-2:270m",
        "input": ["first", "second"],
        "truncate": True,
        "keep_alive": "0",
    }
