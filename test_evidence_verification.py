from datetime import datetime, timezone

import pytest

import evidence_verification as evidence


def _source(**overrides):
    value = {
        "citation_id": "S1",
        "title": "Official report",
        "url": "https://example.org/report",
        "domain": "example.org",
        "source_class": "government-domain",
        "page_status": "extracted",
        "snippet": "A short search result.",
        "published_at": "2026-01-01",
        "updated_at": "2026-02-01T12:00:00Z",
        "retrieved_at": "2026-11-07T10:00:00Z",
        "extracted_at": "2026-11-07T10:01:00Z",
    }
    value.update(overrides)
    return value


def test_normalize_source_preserves_provenance_and_distinguishes_evidence_level():
    normalized = evidence.normalize_source(_source())

    assert normalized["citation_id"] == "S1"
    assert normalized["publisher"] == "example.org"
    assert normalized["evidence_level"] == "extracted_page"
    assert normalized["published_at"] == "2026-01-01T00:00:00+00:00"
    assert normalized["updated_at"] == "2026-02-01T12:00:00+00:00"
    assert normalized["retrieved_at"] == "2026-11-07T10:00:00+00:00"
    assert normalized["extracted_at"] == "2026-11-07T10:01:00+00:00"


def test_normalize_source_does_not_treat_retrieval_as_content_evidence():
    snippet = evidence.normalize_source(
        _source(page_status="not_fetched", published_at=None, updated_at=None)
    )
    unavailable = evidence.normalize_source(
        _source(page_status="unavailable:Timeout", snippet="")
    )

    assert snippet["evidence_level"] == "search_snippet_only"
    assert unavailable["evidence_level"] == "unavailable_or_partial"


def test_normalize_source_rejects_invalid_ids_and_unsafe_urls():
    with pytest.raises(evidence.EvidenceError):
        evidence.normalize_source(_source(citation_id="../S1"))
    normalized = evidence.normalize_source(
        _source(url="https://user:password@example.org/report")
    )
    assert normalized["url"] == ""


def test_normalize_sources_skips_invalid_entries_and_deduplicates_ids():
    normalized = evidence.normalize_sources([
        _source(),
        _source(url="https://example.org/duplicate"),
        {"citation_id": "bad", "url": "https://example.org"},
        "not a source",
    ])

    assert len(normalized) == 1
    assert normalized[0]["citation_id"] == "S1"


def test_freshness_uses_updated_or_published_date_not_retrieval_time():
    source = _source(
        updated_at=None,
        published_at="2026-01-01",
        retrieved_at="2026-11-07T10:00:00Z",
    )
    result = evidence.assess_source_freshness(
        source,
        max_age_days=90,
        as_of="2026-11-07T00:00:00Z",
    )

    assert result["status"] == "stale"
    assert result["reference_kind"] == "published_at"
    assert result["age_days"] == 310


def test_freshness_prefers_updated_date_and_handles_unknown_policy_or_date():
    source = _source(updated_at="2026-11-01", published_at="2020-01-01")
    fresh = evidence.assess_source_freshness(
        source, max_age_days=30, as_of="2026-11-07"
    )
    not_assessed = evidence.assess_source_freshness(source, max_age_days=None)
    unknown = evidence.assess_source_freshness(
        _source(updated_at=None, published_at=None, retrieved_at="2026-11-07"),
        max_age_days=30,
        as_of="2026-11-07",
    )

    assert fresh["status"] == "fresh"
    assert fresh["reference_kind"] == "updated_at"
    assert not_assessed["status"] == "not_assessed"
    assert unknown["status"] == "unknown"


def test_freshness_flags_future_dated_metadata_and_validates_policy():
    future = evidence.assess_source_freshness(
        _source(updated_at="2027-01-01"),
        max_age_days=30,
        as_of="2026-11-07",
    )
    assert future["status"] == "future_dated"

    for invalid in (0, -1, 36501, True, "30"):
        with pytest.raises(evidence.EvidenceError):
            evidence.assess_source_freshness(_source(), max_age_days=invalid)


def test_claim_candidates_are_sentence_level_and_never_claim_semantic_verification():
    candidates = evidence.build_claim_candidates(
        "First claim [S1]. Second claim [S2]. Third claim.",
        [_source(), _source(citation_id="S2", page_status="not_fetched")],
    )

    assert [item["claim_id"] for item in candidates] == ["C1", "C2", "C3"]
    assert candidates[0]["source_ids"] == ["S1"]
    assert candidates[0]["verification_status"] == "UNVERIFIED"
    assert candidates[0]["semantic_support"] == "not_evaluated"
    assert candidates[0]["granularity"] == "sentence_level_candidate"
    assert candidates[1]["evidence"][0]["evidence_level"] == "search_snippet_only"
    assert candidates[2]["citation_status"] == "uncited"


def test_claim_candidates_distinguish_invalid_citations_and_bound_claim_count():
    candidates = evidence.build_claim_candidates(
        "Invalid [S99]. More [S1]. Last [S1].",
        [_source()],
        max_claims=2,
    )

    assert len(candidates) == 2
    assert candidates[0]["invalid_source_ids"] == ["S99"]
    assert candidates[0]["citation_status"] == "invalid_reference"


def test_claim_candidates_rejects_invalid_inputs():
    with pytest.raises(evidence.EvidenceError):
        evidence.build_claim_candidates(None, [])
    with pytest.raises(evidence.EvidenceError):
        evidence.build_claim_candidates("Claim.", [], max_claims=0)


def test_structured_contradiction_detector_finds_potential_conflicts():
    found = evidence.detect_structured_contradictions([
        {
            "claim_id": "C1",
            "subject": "Application deadline",
            "predicate": "is",
            "object": "2026-11-01",
            "source_ids": ["S1"],
        },
        {
            "claim_id": "C2",
            "subject": "application deadline",
            "predicate": "is",
            "object": "2026-11-15",
            "source_ids": ["S2"],
        },
    ])

    assert len(found) == 1
    assert found[0]["status"] == "POTENTIAL_CONTRADICTION"
    assert found[0]["claim_ids"] == ["C1", "C2"]
    assert found[0]["source_ids"] == ["S1", "S2"]
    assert found[0]["requires_review"] is True


def test_structured_contradiction_detector_ignores_same_value_or_different_subject():
    found = evidence.detect_structured_contradictions([
        {"claim_id": "C1", "subject": "A", "predicate": "status", "object": "open"},
        {"claim_id": "C2", "subject": "A", "predicate": "status", "object": "open"},
        {"claim_id": "C3", "subject": "B", "predicate": "status", "object": "closed"},
    ])
    assert found == []


def test_structured_contradiction_detector_respects_disjoint_validity_periods():
    found = evidence.detect_structured_contradictions([
        {
            "claim_id": "C1", "subject": "policy", "predicate": "status", "object": "active",
            "valid_from": "2020-01-01", "valid_until": "2021-12-31",
        },
        {
            "claim_id": "C2", "subject": "policy", "predicate": "status", "object": "inactive",
            "valid_from": "2022-01-01", "valid_until": "2023-12-31",
        },
    ])
    assert found == []


def test_structured_contradiction_detector_marks_unknown_time_as_potential():
    found = evidence.detect_structured_contradictions([
        {"claim_id": "C1", "subject": "policy", "predicate": "status", "object": "active"},
        {"claim_id": "C2", "subject": "policy", "predicate": "status", "object": "inactive"},
    ])
    assert len(found) == 1
    assert found[0]["temporal_overlap"] == "unknown"


def test_structured_contradiction_detector_does_not_infer_structure_from_prose():
    found = evidence.detect_structured_contradictions([
        {"claim_id": "C1", "text": "Policy A is active."},
        {"claim_id": "C2", "text": "Policy A is inactive."},
    ])
    assert found == []


def test_freshness_rejects_invalid_source_and_as_of_values():
    with pytest.raises(evidence.EvidenceError):
        evidence.assess_source_freshness(None, max_age_days=30)
    with pytest.raises(evidence.EvidenceError):
        evidence.assess_source_freshness(
            _source(), max_age_days=30, as_of="not-a-date"
        )
