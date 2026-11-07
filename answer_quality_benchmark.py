"""Deterministic regression benchmark for Oracle's answer-quality signals.

The benchmark measures citation classification and source availability only.
It deliberately does not score semantic entailment or factual truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import answer_quality

DEFAULT_DATASET = Path(__file__).parent / "benchmarks" / "answer_quality_cases.json"
LABELS = ("citation_present_unverified", "uncited", "invalid_reference")


class BenchmarkError(ValueError):
    """Raised when a benchmark dataset is malformed."""


def load_dataset(path: str | Path = DEFAULT_DATASET) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"Unable to load benchmark dataset: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise BenchmarkError("Unsupported benchmark dataset schema.")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkError("Benchmark dataset must contain at least one case.")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise BenchmarkError("Every benchmark case must be an object.")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise BenchmarkError("Case IDs must be non-empty and unique.")
        seen.add(case_id)
        if not isinstance(case.get("answer"), str) or not isinstance(case.get("sources"), list):
            raise BenchmarkError(f"Case {case_id} has invalid answer or sources.")
        expected = case.get("expected_statuses")
        if not isinstance(expected, list) or any(label not in LABELS for label in expected):
            raise BenchmarkError(f"Case {case_id} has invalid expected_statuses.")
    return data


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def run_benchmark(dataset: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dataset if dataset is not None else load_dataset()
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not data["cases"]:
        raise BenchmarkError("A non-empty benchmark dataset is required.")

    results = []
    confusion = {expected: {actual: 0 for actual in LABELS} for expected in LABELS}
    correct = 0
    total = 0
    extracted_refs = 0
    snippet_refs = 0
    for case in data["cases"]:
        assessment = answer_quality.assess_claim_citations(
            case["answer"], case["sources"]
        )
        expected = list(case["expected_statuses"])
        actual = [claim["citation_status"] for claim in assessment["claims"]]
        if len(expected) != len(actual):
            raise BenchmarkError(
                f"Case {case['id']} expected {len(expected)} claims but assessor found {len(actual)}."
            )
        for expected_label, actual_label in zip(expected, actual):
            total += 1
            correct += expected_label == actual_label
            confusion[expected_label][actual_label] += 1
        extracted_refs += assessment["extracted_page_references"]
        snippet_refs += assessment["snippet_only_references"]
        results.append({
            "id": case["id"],
            "passed": expected == actual,
            "expected_statuses": expected,
            "actual_statuses": actual,
            "claim_count": assessment["claim_count"],
            "citation_coverage": assessment["citation_coverage"],
            "extracted_page_references": assessment["extracted_page_references"],
            "snippet_only_references": assessment["snippet_only_references"],
        })

    per_label = {}
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in LABELS if other != label)
        fn = sum(confusion[label][other] for other in LABELS if other != label)
        per_label[label] = _prf(tp, fp, fn)

    macro_f1 = sum(item["f1"] for item in per_label.values()) / len(LABELS)
    return {
        "benchmark_id": data.get("benchmark_id", "custom"),
        "schema_version": data.get("schema_version", 1),
        "assessment_scope": "citation_integrity_and_source_availability_only",
        "semantic_entailment_evaluated": False,
        "factual_truth_evaluated": False,
        "case_count": len(results),
        "claim_count": total,
        "exact_case_pass_rate": round(
            sum(item["passed"] for item in results) / len(results), 4
        ),
        "claim_classification_accuracy": round(correct / total, 4) if total else 1.0,
        "macro_f1": round(macro_f1, 4),
        "per_label": per_label,
        "confusion_matrix": confusion,
        "evidence_references": {
            "extracted_page": extracted_refs,
            "search_snippet_only": snippet_refs,
        },
        "cases": results,
        "limitations": list(data.get("limitations", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, help="Optional path for a JSON report.")
    args = parser.parse_args()
    report = run_benchmark(load_dataset(args.dataset))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["exact_case_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
