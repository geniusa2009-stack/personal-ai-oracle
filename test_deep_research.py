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
    monkeypatch.setattr(
        deep_research.semantic_verifier,
        "verify_claims",
        lambda claims, sources: {
            "status": "completed",
            "semantic_entailment_checked": True,
            "factual_truth_verified": False,
            "checked_claim_count": len(claims),
            "unverified_claim_count": 0,
            "results": [{
                "claim_id": claims[0]["claim_id"],
                "status": "SUPPORTED",
                "supported_source_ids": ["S1", "S2"],
                "contradicting_source_ids": [],
                "reason": "Both extracted pages support the finding.",
                "semantic_support": "SUPPORTED",
            }],
            "limitations": ["Model-assisted evidence judgment; not factual proof."],
        },
    )

    report = deep_research.run_research("water evidence", fetch_pages=True)

    assert report["status"] == "partial"
    assert report["stats"] == {"query_count": 2, "source_count": 2, "page_extracted_count": 2}
    assert len(report["citations"]) == 2
    assert report["key_findings"] == ["Finding one"]
    assert report["limitations"][0] == "The sample is limited to retrieved public sources."
    assert report["citations"][0]["id"] == "S1"
    assert report["citations"][1]["page_status"] == "extracted"
    assert report["sources"][0]["retrieved_at"]
    assert report["sources"][0]["extracted_at"]
    assert report["sources"][0]["evidence_level"] == "extracted_page"
    assert report["evidence_summary"]["source_count"] == 2
    assert report["evidence_summary"]["semantic_verification"] == "completed"
    assert len(report["claim_records"]) == 1
    assert report["evidence_manifest"][0]["evidence_level"] == "extracted_page"
    assert report["semantic_verification"]["semantic_entailment_checked"] is True
    assert report["semantic_verification"]["factual_truth_verified"] is False
    assert report["claim_records"][0]["verification_status"] == "SUPPORTED"
    assert report["claim_records"][0]["supported_source_ids"] == ["S1", "S2"]
    assert report["freshness_assessment"]["profile"] == "general"
    assert report["freshness_assessment"]["counts"]["not_assessed"] == 2
    assert report["sources"][0]["freshness"]["status"] == "not_assessed"


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
    {"freshness_profile": "weekly"},
])
def test_research_rejects_invalid_limits(kwargs):
    options = {"query": "valid query"}
    options.update(kwargs)
    with pytest.raises(deep_research.ResearchError):
        deep_research.run_research(**options)


def test_compact_report_json_is_valid_bounded_and_keeps_source_references():
    report = {
        "status": "success",
        "query": "q" * 500,
        "queries": ["query " * 40] * 4,
        "answer": "answer " * 2000,
        "key_findings": ["finding " * 100] * 8,
        "limitations": ["limitation " * 100] * 8,
        "citations": [
            {"id": f"S{i}", "title": "Title " * 40, "url": f"https://example{i}.com/" + "x" * 1000}
            for i in range(1, 9)
        ],
        "sources": [
            {
                "citation_id": f"S{i}",
                "title": "Title " * 40,
                "url": f"https://example{i}.com/" + "x" * 1000,
                "domain": f"example{i}.com",
                "snippet": "Snippet " * 100,
                "page_status": "extracted",
                "source_class": "general-web",
            }
            for i in range(1, 9)
        ],
        "citation_validation": {"valid_source_ids": [f"S{i}" for i in range(1, 9)], "invalid_source_ids": []},
        "stats": {"source_count": 8},
        "freshness_assessment": {
            "profile": "pricing",
            "policy_source": "explicit",
            "max_age_days": 7,
            "assessed_source_count": 8,
            "counts": {"fresh": 4, "stale": 2, "unknown": 2, "future_dated": 0, "not_assessed": 0},
            "results": [{"citation_id": "S1", "status": "stale", "age_days": 90}],
        },
    }

    serialized = deep_research.compact_report_json(report, max_bytes=9000)
    restored = json.loads(serialized)

    assert len(serialized.encode("utf-8")) <= 9000
    assert restored["context_truncated"] is True
    assert restored["citations"]
    assert restored["freshness_assessment"]["profile"] == "pricing"
    assert restored["freshness_assessment"]["counts"]["stale"] == 2
    assert all(citation["id"] in {s["citation_id"] for s in restored["sources"]} for citation in restored["citations"])


def test_compact_report_rejects_too_small_or_invalid_byte_limits():
    for maximum in (0, 100, 12001, True):
        with pytest.raises(deep_research.ResearchError):
            deep_research.compact_report_json({"answer": "test"}, max_bytes=maximum)


def test_compact_report_fallback_keeps_json_valid_at_minimum_size():
    report = {
        "status": "success",
        "answer": "معلومة مهمة " * 3000,
        "citations": [{"id": f"S{i}", "title": "x" * 300, "url": "https://example.com/" + "x" * 1000} for i in range(1, 9)],
        "sources": [],
        "citation_validation": {"valid_source_ids": [], "invalid_source_ids": []},
    }

    serialized = deep_research.compact_report_json(report, max_bytes=1024)
    restored = json.loads(serialized)

    assert len(serialized.encode("utf-8")) <= 1024
    assert restored["context_truncated"] is True
    assert restored["freshness_assessment"]["profile"] == "general"
    assert "answer" in restored


def test_research_stops_repeated_remote_waits_when_mac_agent_is_offline(monkeypatch):
    from cloud_client import CloudAgentUnavailable

    monkeypatch.setenv("ORACLE_RUNTIME_MODE", "cloud")
    sources = [
        {"url": f"https://example{i}.com/", "page_status": "not_fetched", "title": "x", "snippet": ""}
        for i in range(1, 5)
    ]
    calls = []

    def unavailable(url, task):
        calls.append(url)
        raise CloudAgentUnavailable("Mac agent offline")

    monkeypatch.setattr(deep_research, "_navigate", unavailable)
    deep_research._fetch_pages(sources, maximum=4, task="research")

    assert len(calls) == 1
    assert sources[0]["page_status"] == "unavailable:CloudAgentUnavailable"
    assert all(item["page_status"] == "unavailable:MacAgentOffline" for item in sources[1:])


def test_claim_evidence_maps_valid_invalid_and_missing_citations():
    claims = deep_research.map_claim_evidence(
        "Claim A is supported [S1]. Claim B has no citation. Claim C refers to [S99].",
        ["S1", "S2"],
    )
    assert [item["citation_status"] for item in claims] == [
        "cited", "uncited", "invalid_reference"
    ]
    assert claims[0]["source_ids"] == ["S1"]
    assert claims[1]["source_ids"] == []
    assert claims[2]["invalid_source_ids"] == ["S99"]


def test_claim_evidence_rejects_invalid_source_ids_and_limits():
    with pytest.raises(deep_research.ResearchError):
        deep_research.map_claim_evidence("claim", ["not-a-source"])
    with pytest.raises(deep_research.ResearchError):
        deep_research.map_claim_evidence("claim", ["S1"], max_claims=0)


def test_search_results_preserve_provider_date_hints_as_unverified_metadata(monkeypatch):
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "Dated source",
            "url": "https://example.org/report",
            "snippet": "Summary",
            "source": "test",
            "publisher": "Example Publisher",
            "published_at": "2026-09-01",
            "updated_at": "2026-10-01T00:00:00Z",
        }],
    )

    sources = deep_research._collect_search_results(["query"], 3)

    assert sources[0]["publisher"] == "Example Publisher"
    assert sources[0]["published_at"] == "2026-09-01"
    assert sources[0]["updated_at"] == "2026-10-01T00:00:00Z"
    assert sources[0]["date_metadata_origin"] == "search_provider"


def test_research_can_disable_semantic_verification_and_keeps_candidates_unverified(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "One result",
            "url": "https://example.com/",
            "snippet": "Snippet content",
            "source": "test",
        }],
    )
    monkeypatch.setattr(
        deep_research.ai_core,
        "chat",
        lambda *args, **kwargs: json.dumps({
            "answer": "Claim [S1].",
            "cited_source_ids": ["S1"],
        }),
    )
    calls = []
    monkeypatch.setattr(
        deep_research.semantic_verifier,
        "verify_claims",
        lambda *_args, **_kwargs: calls.append(True),
    )

    report = deep_research.run_research(
        "test",
        max_queries=1,
        fetch_pages=False,
        verify_claims=False,
    )

    assert calls == []
    assert report["semantic_verification"]["status"] == "not_performed"
    assert report["claim_records"][0]["verification_status"] == "UNVERIFIED"


def test_research_rejects_non_boolean_semantic_verification_flag():
    with pytest.raises(deep_research.ResearchError):
        deep_research.run_research("valid query", verify_claims="yes")


def test_research_applies_domain_freshness_policy_and_flags_old_sources(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["scholarship deadline query"])
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "Scholarship application page",
            "url": "https://example.org/scholarship",
            "snippet": "Applications close on 30 November.",
            "source": "test",
            "published_at": "2026-01-01",
        }],
    )
    monkeypatch.setattr(
        deep_research,
        "_navigate",
        lambda *_: {
            "status": "success",
            "result": {
                "title": "Scholarship application page",
                "text": "The application deadline is 30 November.",
                "http_status": 200,
            },
        },
    )
    monkeypatch.setattr(
        deep_research.ai_core,
        "chat",
        lambda *args, **kwargs: json.dumps({
            "answer": "Applications close on 30 November [S1].",
            "cited_source_ids": ["S1"],
        }),
    )
    monkeypatch.setattr(
        deep_research.semantic_verifier,
        "verify_claims",
        lambda claims, sources: {
            "status": "completed",
            "semantic_entailment_checked": True,
            "factual_truth_verified": False,
            "checked_claim_count": 1,
            "unverified_claim_count": 0,
            "results": [{
                "claim_id": "C1",
                "status": "SUPPORTED",
                "supported_source_ids": ["S1"],
                "contradicting_source_ids": [],
                "reason": "The extracted page contains the stated deadline.",
                "semantic_support": "SUPPORTED",
            }],
            "limitations": [],
        },
    )

    report = deep_research.run_research(
        "Find current scholarship deadlines",
        max_queries=1,
        max_sources=1,
    )

    assert report["freshness_assessment"]["profile"] == "scholarship_deadline"
    assert report["freshness_assessment"]["policy_source"] == "query_hint"
    assert report["freshness_assessment"]["matched_hint"] == "scholarship"
    assert report["freshness_assessment"]["counts"]["stale"] == 1
    assert report["sources"][0]["freshness"]["status"] == "stale"
    assert report["citations"][0]["freshness"]["status"] == "stale"
    assert any("freshness threshold" in item for item in report["limitations"])
    assert report["status"] == "partial"



def test_research_correction_repairs_invalid_citation_without_repeating_search(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    search_calls = []
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: (
            search_calls.append(True)
            or [{
                "title": "Primary source",
                "url": "https://example.com/report",
                "snippet": "The report states the verified result.",
                "source": "test",
            }]
        ),
    )
    model_outputs = [
        json.dumps({
            "answer": "The result is confirmed [S99].",
            "cited_source_ids": ["S99"],
        }),
        json.dumps({
            "answer": "The report records the result [S1].",
            "cited_source_ids": ["S1"],
            "key_findings": ["The result is recorded."],
            "limitations": [],
        }),
    ]
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(messages)
        return model_outputs.pop(0)

    monkeypatch.setattr(deep_research.ai_core, "chat", fake_chat)

    report = deep_research.run_research(
        "Check a reported result",
        max_queries=1,
        max_sources=1,
        fetch_pages=False,
    )

    assert len(search_calls) == 1
    assert len(calls) == 2
    assert report["answer"] == "The report records the result [S1]."
    assert report["citation_validation"]["valid_source_ids"] == ["S1"]
    assert report["citation_validation"]["invalid_source_ids"] == []
    assert report["self_correction"]["status"] == "corrected"
    assert report["self_correction"]["retry_count"] == 1
    assert report["self_correction"]["corrected"] is True
    assert report["self_correction"]["stop_reason"] == "validated_after_retry"
    assert report["self_correction"]["final_issue_codes"] == []
    assert "previous_model_output_untrusted" in calls[1][1]["content"]


def test_research_correction_stops_on_repeated_invalid_output(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    search_calls = []
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: (
            search_calls.append(True)
            or [{
                "title": "Primary source",
                "url": "https://example.com/",
                "snippet": "Evidence.",
                "source": "test",
            }]
        ),
    )
    invalid = json.dumps({
        "answer": "Unsupported [S99].",
        "cited_source_ids": ["S99"],
    })
    chat = Mock(return_value=invalid)
    monkeypatch.setattr(deep_research.ai_core, "chat", chat)

    report = deep_research.run_research(
        "Check a result",
        max_queries=1,
        max_sources=1,
        fetch_pages=False,
        max_correction_retries=2,
    )

    assert chat.call_count == 2
    assert len(search_calls) == 1
    assert report["citation_validation"]["invalid_source_ids"] == ["S99"]
    assert report["self_correction"]["stop_reason"] == "repeated_output"
    assert report["self_correction"]["attempt_count"] == 2
    assert report["self_correction"]["retry_count"] == 1
    assert "invalid_citation_ids" in report["self_correction"]["final_issue_codes"]


def test_provider_error_is_not_retried_during_research_synthesis(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "Source",
            "url": "https://example.com/",
            "snippet": "Evidence.",
            "source": "test",
        }],
    )
    chat = Mock(return_value="(تعذّر التشغيل: provider unavailable)")
    monkeypatch.setattr(deep_research.ai_core, "chat", chat)

    report = deep_research.run_research(
        "Research this",
        max_queries=1,
        max_sources=1,
        fetch_pages=False,
    )

    assert chat.call_count == 1
    assert report["self_correction"]["stop_reason"] == "non_retryable_issue"
    assert report["self_correction"]["final_issue_codes"] == ["provider_error"]


def test_research_can_disable_bounded_correction(monkeypatch):
    monkeypatch.setattr(deep_research, "_query_plan", lambda *_: ["query"])
    monkeypatch.setattr(
        deep_research.search,
        "web_search",
        lambda *_args, **_kwargs: [{
            "title": "Source",
            "url": "https://example.com/",
            "snippet": "Evidence.",
            "source": "test",
        }],
    )
    response = json.dumps({
        "answer": "Unsupported [S99].",
        "cited_source_ids": ["S99"],
    })
    chat = Mock(return_value=response)
    monkeypatch.setattr(deep_research.ai_core, "chat", chat)

    report = deep_research.run_research(
        "Research this",
        max_queries=1,
        max_sources=1,
        fetch_pages=False,
        max_correction_retries=0,
    )

    assert chat.call_count == 1
    assert report["self_correction"]["retry_count"] == 0
    assert report["self_correction"]["stop_reason"] == "retry_limit_reached"


def test_research_validates_bounded_correction_budget():
    for retries in (-1, 3, True):
        with pytest.raises(deep_research.ResearchError):
            deep_research.run_research("valid query", max_correction_retries=retries)


def test_compact_report_preserves_correction_metadata():
    report = {
        "status": "partial",
        "answer": "A concise result [S1].",
        "self_correction": {
            "status": "corrected",
            "attempt_count": 2,
            "retry_count": 1,
            "corrected": True,
            "stop_reason": "validated_after_retry",
            "final_issue_codes": [],
            "attempts": [],
        },
    }

    compact = json.loads(deep_research.compact_report_json(report, max_bytes=1024))

    assert compact["self_correction"]["status"] == "corrected"
    assert compact["self_correction"]["retry_count"] == 1
    assert compact["self_correction"]["stop_reason"] == "validated_after_retry"
