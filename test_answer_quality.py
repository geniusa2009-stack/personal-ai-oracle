import answer_quality


def _sources():
    return [
        {"citation_id": "S1", "page_status": "extracted"},
        {"citation_id": "S2", "page_status": "not_fetched"},
        {"citation_id": "S3", "page_status": "unavailable:Timeout"},
    ]


def test_assessment_distinguishes_citations_from_semantic_support():
    result = answer_quality.assess_claim_citations(
        "Supported-looking statement [S1]. Snippet-based statement [S2].",
        _sources(),
    )

    assert result["status"] == "citations_present_semantics_unverified"
    assert result["citation_coverage"] == 1.0
    assert result["semantic_entailment_checked"] is False
    assert result["truth_verified"] is False
    assert result["claims"][0]["semantic_support"] == "not_evaluated"
    assert result["claims"][0]["sources"][0]["evidence_level"] == "extracted_page"
    assert result["claims"][1]["sources"][0]["evidence_level"] == "search_snippet_only"


def test_assessment_flags_uncited_and_invalid_claims():
    result = answer_quality.assess_claim_citations(
        "No citation here. Invalid citation [S99]. Valid reference [S1].",
        _sources(),
    )

    assert result["status"] == "needs_citation_review"
    assert result["uncited_claim_count"] == 1
    assert result["invalid_reference_claim_count"] == 1
    assert result["claims"][1]["citation_status"] == "invalid_reference"
    assert result["citation_coverage"] == round(1 / 3, 4)


def test_assessment_handles_empty_answers_and_rejects_bad_inputs():
    result = answer_quality.assess_claim_citations("", _sources())
    assert result["status"] == "no_claims_detected"
    assert result["citation_coverage"] == 0.0

    import pytest
    with pytest.raises(ValueError):
        answer_quality.assess_claim_citations(None, _sources())
    with pytest.raises(ValueError):
        answer_quality.assess_claim_citations("claim", _sources(), max_claims=0)


def test_assessment_ignores_malformed_source_ids():
    result = answer_quality.assess_claim_citations(
        "Claim [S1].", [{"citation_id": "../S1", "page_status": "extracted"}]
    )
    assert result["claims"][0]["citation_status"] == "invalid_reference"
