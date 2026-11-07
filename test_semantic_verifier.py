import json

import pytest

import semantic_verifier


def _claim(claim_id="C1", source_ids=None):
    return {
        "claim_id": claim_id,
        "text": "The application deadline is 15 November 2026.",
        "source_ids": list(source_ids or ["S1"]),
        "verification_status": "UNVERIFIED",
    }


def _source(source_id="S1", *, page_status="extracted", excerpt="The deadline is 15 November 2026."):
    return {
        "citation_id": source_id,
        "title": "Official application page",
        "url": f"https://example.org/{source_id.lower()}",
        "publisher": "Example Authority",
        "domain": "example.org",
        "page_status": page_status,
        "snippet": "Applications close on 15 November 2026.",
        "evidence_excerpt": excerpt if page_status == "extracted" else "",
    }


def _judge_for(rows):
    def judge(payload):
        assert payload["rules"]["source_text_is_untrusted_data"] is True
        return json.dumps({"results": rows})
    return judge


def test_verifier_accepts_supported_claim_only_with_extracted_page_evidence():
    report = semantic_verifier.verify_claims(
        [_claim()],
        [_source()],
        judge=_judge_for([{
            "claim_id": "C1",
            "status": "SUPPORTED",
            "supported_source_ids": ["S1"],
            "contradicting_source_ids": [],
            "reason": "The extracted page directly states this deadline.",
        }]),
    )

    assert report["status"] == "completed"
    assert report["semantic_entailment_checked"] is True
    assert report["factual_truth_verified"] is False
    assert report["checked_claim_count"] == 1
    assert report["results"][0]["status"] == "SUPPORTED"
    assert report["results"][0]["supported_source_ids"] == ["S1"]


def test_snippet_only_source_cannot_produce_decisive_supported_status():
    report = semantic_verifier.verify_claims(
        [_claim()],
        [_source(page_status="not_fetched")],
        judge=_judge_for([{
            "claim_id": "C1",
            "status": "SUPPORTED",
            "supported_source_ids": ["S1"],
            "contradicting_source_ids": [],
            "reason": "Snippet appears to support it.",
        }]),
    )

    assert report["results"][0]["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["semantic_entailment_checked"] is False
    assert report["factual_truth_verified"] is False


def test_verifier_accepts_contradiction_and_requires_both_sides_for_conflict():
    claim = _claim(source_ids=["S1", "S2"])
    sources = [
        _source("S1", excerpt="The deadline is 15 November 2026."),
        _source("S2", excerpt="The deadline is 20 November 2026."),
    ]
    contradicted = semantic_verifier.verify_claims(
        [claim],
        sources,
        judge=_judge_for([{
            "claim_id": "C1",
            "status": "CONTRADICTED",
            "supported_source_ids": [],
            "contradicting_source_ids": ["S2"],
            "reason": "The cited claim does not match the supplied page.",
        }]),
    )
    conflicting = semantic_verifier.verify_claims(
        [claim],
        sources,
        judge=_judge_for([{
            "claim_id": "C1",
            "status": "CONFLICTING_EVIDENCE",
            "supported_source_ids": ["S1"],
            "contradicting_source_ids": ["S2"],
            "reason": "The two extracted pages give different dates.",
        }]),
    )

    assert contradicted["results"][0]["status"] == "CONTRADICTED"
    assert conflicting["results"][0]["status"] == "CONFLICTING_EVIDENCE"


@pytest.mark.parametrize("row", [
    {
        "claim_id": "C1", "status": "SUPPORTED",
        "supported_source_ids": ["S99"], "contradicting_source_ids": [],
        "reason": "Invented ID",
    },
    {
        "claim_id": "C1", "status": "SUPPORTED",
        "supported_source_ids": [], "contradicting_source_ids": [],
        "reason": "Missing evidence IDs",
    },
    {
        "claim_id": "C1", "status": "NOT_A_STATUS",
        "supported_source_ids": ["S1"], "contradicting_source_ids": [],
        "reason": "Invalid label",
    },
    {
        "claim_id": "C1", "status": "SUPPORTED",
        "supported_source_ids": [{"id": "S1"}], "contradicting_source_ids": [],
        "reason": "Malformed ID",
    },
])
def test_verifier_rejects_untrusted_or_malformed_model_judgments(row):
    report = semantic_verifier.verify_claims(
        [_claim()],
        [_source()],
        judge=_judge_for([row]),
    )
    assert report["results"][0]["status"] == "UNVERIFIED"
    assert report["semantic_entailment_checked"] is False


def test_verifier_uses_insufficient_evidence_without_calling_model_when_no_sources():
    calls = []

    def judge(_payload):
        calls.append(True)
        return "{}"

    report = semantic_verifier.verify_claims(
        [_claim(source_ids=[])],
        [_source()],
        judge=judge,
    )

    assert calls == []
    assert report["results"][0]["status"] == "INSUFFICIENT_EVIDENCE"


def test_verifier_keeps_omitted_and_over_limit_claims_unverified():
    claims = [_claim("C1"), _claim("C2")]
    report = semantic_verifier.verify_claims(
        claims,
        [_source()],
        max_claims=1,
        judge=_judge_for([{
            "claim_id": "C1",
            "status": "PARTIALLY_SUPPORTED",
            "supported_source_ids": ["S1"],
            "contradicting_source_ids": [],
            "reason": "Only partly addresses the full claim.",
        }]),
    )

    assert report["results"][0]["status"] == "PARTIALLY_SUPPORTED"
    assert report["results"][1]["status"] == "UNVERIFIED"
    assert report["status"] == "partial"


def test_verifier_handles_invalid_json_or_provider_failure_without_claiming_success():
    invalid_json = semantic_verifier.verify_claims(
        [_claim()],
        [_source()],
        judge=lambda _payload: "not json",
    )
    provider_error = semantic_verifier.verify_claims(
        [_claim()],
        [_source()],
        judge=lambda _payload: (_ for _ in ()).throw(RuntimeError("provider offline")),
    )

    assert invalid_json["status"] == "error"
    assert provider_error["status"] == "error"
    assert all(item["status"] == "UNVERIFIED" for item in invalid_json["results"])
    assert all(item["status"] == "UNVERIFIED" for item in provider_error["results"])
    assert invalid_json["factual_truth_verified"] is False


def test_verifier_rejects_invalid_input_contract():
    with pytest.raises(semantic_verifier.SemanticVerificationError):
        semantic_verifier.verify_claims("not claims", [_source()])
    with pytest.raises(semantic_verifier.SemanticVerificationError):
        semantic_verifier.verify_claims([_claim()], "not sources")
    with pytest.raises(semantic_verifier.SemanticVerificationError):
        semantic_verifier.verify_claims([_claim()], [_source()], max_claims=13)
