import copy

import pytest

import answer_quality_benchmark as benchmark


def test_curated_benchmark_passes_all_cases():
    report = benchmark.run_benchmark()

    assert report["case_count"] == 10
    assert report["exact_case_pass_rate"] == 1.0
    assert report["claim_classification_accuracy"] == 1.0
    assert report["semantic_entailment_evaluated"] is False
    assert report["factual_truth_evaluated"] is False
    assert report["evidence_references"]["extracted_page"] > 0
    assert report["evidence_references"]["search_snippet_only"] > 0


def test_benchmark_detects_classification_regression(monkeypatch):
    original = benchmark.answer_quality.assess_claim_citations

    def changed(answer, sources, **kwargs):
        result = original(answer, sources, **kwargs)
        if result["claims"]:
            result["claims"][0]["citation_status"] = "uncited"
        return result

    monkeypatch.setattr(benchmark.answer_quality, "assess_claim_citations", changed)
    report = benchmark.run_benchmark()

    assert report["exact_case_pass_rate"] < 1.0
    assert report["claim_classification_accuracy"] < 1.0


def test_benchmark_rejects_duplicate_case_ids():
    dataset = benchmark.load_dataset()
    duplicate = copy.deepcopy(dataset)
    duplicate["cases"][1]["id"] = duplicate["cases"][0]["id"]

    with pytest.raises(benchmark.BenchmarkError):
        benchmark.load_dataset_from_data(duplicate)
