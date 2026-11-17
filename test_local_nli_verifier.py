import json

import local_nli_verifier


class FakeNLI:
    def __init__(self, scores):
        self.scores = list(scores)
        self.calls = []

    def score(self, premise, hypothesis):
        self.calls.append((premise, hypothesis))
        return self.scores.pop(0)


def _payload(evidence):
    return {
        "claims": [{
            "claim_id": "C1",
            "claim": "The deadline is 15 November.",
            "evidence": evidence,
        }]
    }


def _evidence(source_id, excerpt, level="extracted_page"):
    return {
        "source_id": source_id,
        "excerpt": excerpt,
        "evidence_level": level,
    }


def test_local_nli_returns_supported_for_extracted_entailing_evidence(monkeypatch):
    model = FakeNLI([{"entailment": 0.91, "contradiction": 0.02, "neutral": 0.07}])
    monkeypatch.setattr(local_nli_verifier, "_model", lambda: model)
    monkeypatch.setenv("ORACLE_NLI_THRESHOLD", "0.80")

    result = json.loads(local_nli_verifier.judge_payload(_payload([
        _evidence("S1", "Applications close on 15 November.")
    ])))

    assert result["results"][0]["status"] == "SUPPORTED"
    assert result["results"][0]["supported_source_ids"] == ["S1"]
    assert len(model.calls) == 1


def test_local_nli_returns_contradicted_for_extracted_contradicting_evidence(monkeypatch):
    model = FakeNLI([{"entailment": 0.03, "contradiction": 0.92, "neutral": 0.05}])
    monkeypatch.setattr(local_nli_verifier, "_model", lambda: model)

    result = json.loads(local_nli_verifier.judge_payload(_payload([
        _evidence("S2", "Applications close on 20 November.")
    ])))

    assert result["results"][0]["status"] == "CONTRADICTED"
    assert result["results"][0]["contradicting_source_ids"] == ["S2"]


def test_local_nli_marks_conflicting_sources_and_ignores_snippets(monkeypatch):
    model = FakeNLI([
        {"entailment": 0.90, "contradiction": 0.02, "neutral": 0.08},
        {"entailment": 0.01, "contradiction": 0.94, "neutral": 0.05},
    ])
    monkeypatch.setattr(local_nli_verifier, "_model", lambda: model)

    result = json.loads(local_nli_verifier.judge_payload(_payload([
        _evidence("S1", "Deadline is 15 November."),
        _evidence("S2", "Deadline is 20 November."),
        _evidence("S3", "Snippet claims 15 November.", level="search_snippet_only"),
    ])))

    assert result["results"][0]["status"] == "CONFLICTING_EVIDENCE"
    assert result["results"][0]["supported_source_ids"] == ["S1"]
    assert result["results"][0]["contradicting_source_ids"] == ["S2"]
    assert len(model.calls) == 2


def test_local_nli_requires_explicit_model_directory(monkeypatch):
    monkeypatch.delenv("ORACLE_NLI_MODEL_DIR", raising=False)
    try:
        local_nli_verifier._model()
    except local_nli_verifier.LocalNLIError as exc:
        assert "ORACLE_NLI_MODEL_DIR" in str(exc)
    else:
        raise AssertionError("Expected explicit model directory requirement")


def test_local_nli_threshold_is_bounded(monkeypatch):
    monkeypatch.setenv("ORACLE_NLI_THRESHOLD", "0.2")
    try:
        local_nli_verifier._threshold()
    except local_nli_verifier.LocalNLIError:
        pass
    else:
        raise AssertionError("Expected threshold validation")



def test_local_nli_marks_claim_unverified_when_pair_budget_is_exhausted(monkeypatch):
    model = FakeNLI([
        {"entailment": 0.93, "contradiction": 0.02, "neutral": 0.05},
    ])
    monkeypatch.setattr(local_nli_verifier, "_model", lambda: model)
    monkeypatch.setattr(local_nli_verifier, "MAX_PAIRS_PER_RUN", 1)
    payload = {
        "claims": [
            {
                "claim_id": "C1",
                "claim": "Claim one",
                "evidence": [_evidence("S1", "Evidence one")],
            },
            {
                "claim_id": "C2",
                "claim": "Claim two",
                "evidence": [_evidence("S2", "Evidence two")],
            },
        ]
    }

    result = json.loads(local_nli_verifier.judge_payload(payload))

    assert result["results"][0]["status"] == "SUPPORTED"
    assert result["results"][1]["status"] == "UNVERIFIED"
    assert len(model.calls) == 1
