import json
from unittest.mock import Mock

import pytest

import deep_research


def test_normalize_url_removes_tracking_and_fragment():
    assert deep_research._normalize_url(
        "HTTPS://Example.COM:443/research?utm_source=news&id=7&fbclid=abc#section"
    ) == "https://example.com/research?id=7"


def test_normalize_url_rejects_non_http_and_credentials():
    for url in (
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pass@example.com/path",
        "not a url",
    ):
        assert deep_research._normalize_url(url) == ""


def test_query_plan_falls_back_and_deduplicates(monkeypatch):
    monkeypatch.setattr(
        deep_research.ai_core,
        "chat",
        lambda *args, **kwargs: json.dumps({
            "queries": ["official report about water", "official report about water", "independent study"]
        }),
    )

    queries = deep_research._query_plan("water crisis", 3, None)

    assert queries == ["water crisis", "official report about water", "independent study"]


def test_search_results_deduplicate_normalized_urls(monkeypatch):
    responses = [
        {"title": "Official source", "url": "https://example.com/page?utm_source=a#top", "snippet": "first", "source": "a"},
        {"title": "Same source", "url": "https://EXAMPLE.com/page?utm_medium=b", "snippet": "second", "source": "b"},
        {"title": "Other source", "url": "https://example.org/", "snippet": "other", "source": "c"},
    ]
    monkeypatch.setattr(deep_research.search, "web_search", lambda *_args, **_kwargs: responses)

    sources = deep_research._collect_search_results(["query"], 8)

    assert len(sources) == 2
    assert sources[0]["url"] == "https://example.com/page"
    assert sources[0]["search_providers"] == ["a", "b"]
    assert sources[0]["snippet"] == "first"


def test_research_runs_multiple_queries_fetches_pages_and_validates_citations(monkeypatch):
    monkeypatch.setattr(
        deep_research,
        "_query_plan",
        lambda query, maximum, scope: ["first query", "second query"],
    )
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda query, max_results: [
            {
                "title": f"Result for {query}",
                "url": f"https://example{1 if query == 'first query' else 2}.org/article",
                "snippet": "Search evidence",
                "source": "test",
            }
        ],
    )
    monkeypatch.setattr(
        deep_research,
        "_navigate",
        lambda url, task: {
            "status": "success",
            "result": {"title": "Fetched title", "text": "Extracted evidence", "http_status": 200},
        },
    )
    monkeypatch.setattr(
        deep_research.ai_core,
        "chat",
        lambda *args, **kwargs: json.dumps({
            "answer": "Finding supported by [S1] and [S2].",
            "key_findings": ["Finding one"],
            "limitations": ["The sample is limited to retrieved public sources."],
            "cited_source_ids": ["S1", "S2"],
        }),
    )

    report = deep_research.run_research("water evidence", fetch_pages=True)

    assert report["status"] == "partial"
    assert report["stats"] == {"query_count": 2, "source_count": 2, "page_extracted_count": 2}
    assert len(report["citations"]) == 2
    assert report["key_findings"] == ["Finding one"]
    assert report["limitations"][0] == "The sample is limited to retrieved public sources."
    assert report["citations"][0]["id"] == "S1"
    assert report["citations"][1]["page_status"] == "extracted"


def test_research_flags_invalid_model_citations(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "One result", "url": "https://example.com/", "snippet": "Evidence", "source": "test"
        }],
    )
    monkeypatch.setattr(
        deep_research.ai_core,
        "chat",
        lambda *args, **kwargs: json.dumps({
            "answer": "Unsupported [S99].",
            "cited_source_ids": ["S99"],
        }),
    )

    report = deep_research.run_research("test", max_queries=1, fetch_pages=False)

    assert report["status"] == "partial"
    assert report["citation_validation"]["invalid_source_ids"] == ["S99"]
    assert report["citations"] == []


def test_research_handles_mac_browser_unavailable_without_losing_search_results(monkeypatch):
    monkeypatch.setenv("ORACLE_RUNTIME_MODE", "cloud")
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "Search result", "url": "https://example.com/", "snippet": "Snippet", "source": "test"
        }],
    )
    monkeypatch.setattr(
        deep_research,
        "_navigate",
        lambda *_: (_ for _ in ()).throw(RuntimeError("Mac agent offline")),
    )
    monkeypatch.setattr(
        deep_research.ai_core,
        "chat",
        lambda *args, **kwargs: json.dumps({
            "answer": "Based on the available snippet [S1].",
            "cited_source_ids": ["S1"],
        }),
    )

    report = deep_research.run_research("test", max_queries=1, fetch_pages=True)

    assert report["status"] == "partial"
    assert report["sources"][0]["page_status"] == "unavailable:RuntimeError"
    assert report["citations"][0]["id"] == "S1"


@pytest.mark.parametrize("kwargs", [
    {"max_queries": 0},
    {"max_queries": 5},
    {"max_sources": 13},
    {"fetch_pages": "yes"},
])
def test_research_rejects_invalid_limits(kwargs):
    options = {"query": "valid query"}
    options.update(kwargs)
    with pytest.raises(deep_research.ResearchError):
        deep_research.run_research(**options)
