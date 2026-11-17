import json

import local_nli_verifier
import semantic_verifier


def test_semantic_verifier_selects_local_nli_only_when_explicitly_configured(monkeypatch):
    monkeypatch.setenv("ORACLE_SEMANTIC_VERIFIER", "local_nli")
    calls = []

    def local_judge(payload):
        calls.append(payload)
        return json.dumps({
            "results": [{
                "claim_id": "C1",
                "status": "SUPPORTED",
                "supported_source_ids": ["S1"],
                "contradicting_source_ids": [],
                "reason": "Local NLI test judgment.",
                "evaluation_kind": "local_nli_assessment",
            }]
        })

    monkeypatch.setattr(local_nli_verifier, "judge_payload", local_judge)
    report = semantic_verifier.verify_claims(
        [{
            "claim_id": "C1",
            "text": "The deadline is 15 November 2026.",
            "source_ids": ["S1"],
        }],
        [{
            "citation_id": "S1",
            "title": "Official page",
            "url": "https://example.org/deadline",
            "publisher": "Example Authority",
            "domain": "example.org",
            "page_status": "extracted",
            "evidence_excerpt": "The deadline is 15 November 2026.",
            "snippet": "",
        }],
    )

    assert len(calls) == 1
    assert report["status"] == "completed"
    assert report["semantic_entailment_checked"] is True
    assert report["factual_truth_verified"] is False
    assert report["results"][0]["evaluation_kind"] == "local_nli_assessment"


def test_local_nli_selection_does_not_fall_back_to_hosted_model(monkeypatch):
    monkeypatch.setenv("ORACLE_SEMANTIC_VERIFIER", "local_nli")
    monkeypatch.delenv("ORACLE_NLI_MODEL_DIR", raising=False)

    # A local runtime failure is caught by the existing fail-closed verifier.
    report = semantic_verifier.verify_claims(
        [{
            "claim_id": "C1",
            "text": "The deadline is 15 November 2026.",
            "source_ids": ["S1"],
        }],
        [{
            "citation_id": "S1",
            "title": "Official page",
            "url": "https://example.org/deadline",
            "publisher": "Example Authority",
            "domain": "example.org",
            "page_status": "extracted",
            "evidence_excerpt": "The deadline is 15 November 2026.",
            "snippet": "",
        }],
    )

    assert report["status"] == "error"
    assert report["results"][0]["status"] == "UNVERIFIED"
    assert report["factual_truth_verified"] is False
