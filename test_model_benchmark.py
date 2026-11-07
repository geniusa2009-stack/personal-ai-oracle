import json
import time

import pytest

import db
import model_benchmark
import model_observability


def _use_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "model-benchmark.db"))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")


def _suite():
    return model_benchmark.BenchmarkSuite(
        "test-suite-v1",
        (
            model_benchmark.BenchmarkCase(
                "case-one",
                "reasoning",
                ({"role": "user", "content": "Compute 2 + 2."},),
                expected_contains=("4",),
            ),
            model_benchmark.BenchmarkCase(
                "case-two",
                "fast",
                ({"role": "user", "content": "Classify a happy outcome."},),
                expected_contains=("positive",),
                forbidden_contains=("negative",),
            ),
            model_benchmark.BenchmarkCase(
                "case-three",
                "writing",
                ({"role": "user", "content": "Reply with the word done."},),
                expected_contains=("done",),
            ),
        ),
    )


def test_load_bundled_suite_is_synthetic_and_bounded():
    suite = model_benchmark.load_suite()

    assert suite.suite_id == "oracle-model-smoke-v1"
    assert 1 <= len(suite.cases) <= model_benchmark.MAX_CASES
    assert len({case.case_id for case in suite.cases}) == len(suite.cases)
    assert all(case.expected_contains for case in suite.cases)


def test_benchmark_records_latency_quality_and_outcomes_without_prompt_or_completion(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    suite = _suite()
    candidates = (
        model_benchmark.ModelCandidate("ollama", "fast-model"),
        model_benchmark.ModelCandidate("ollama", "slow-model"),
    )

    def runner(candidate, request):
        prompt = request.to_messages()[-1]["content"]
        if candidate.model == "slow-model":
            time.sleep(0.006)
            return "not the required output"
        return {
            "Compute 2 + 2.": "4",
            "Classify a happy outcome.": "positive",
            "Reply with the word done.": "done",
        }[prompt]

    run = model_benchmark.run_benchmark(
        "owner:one",
        suite,
        candidates,
        runner=runner,
    )
    results = model_benchmark.list_results("owner:one", run_id=run.run_id, limit=20)

    assert run.status == "completed"
    assert run.request_count == 6
    assert run.success_count == 6
    assert run.failure_count == 0
    assert len(results) == 6
    assert all(item["outcome"] == "success" for item in results)
    assert all(item["quality_score"] is not None for item in results)
    assert {item["evaluator_id"] for item in results} == {"phrase_rubric_v1"}
    assert all(item["output_chars"] > 0 for item in results)

    serialized = json.dumps(results)
    assert "Compute 2 + 2" not in serialized
    assert "not the required output" not in serialized
    assert "positive" not in serialized
    conn = db.get_conn()
    try:
        columns = {
            item["name"]
            for item in conn.execute("PRAGMA table_info(oracle_model_benchmark_results)")
        }
        assert not {"prompt", "completion", "messages", "answer"} & columns
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM oracle_model_benchmark_runs WHERE scope='owner:one'"
        ).fetchone()["c"] == 1
    finally:
        conn.close()


def test_hosted_models_require_explicit_allow_remote_before_runner_is_called(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    called = []

    def runner(candidate, request):
        called.append(candidate)
        return "4"

    with pytest.raises(model_benchmark.ModelBenchmarkError, match="allow_remote=True"):
        model_benchmark.run_benchmark(
            "owner:one",
            _suite(),
            [model_benchmark.ModelCandidate("openrouter", "hosted-model")],
            runner=runner,
        )
    assert called == []
    assert model_benchmark.list_results("owner:one") == []


def test_runner_failures_are_recorded_without_exception_text(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)

    def runner(_candidate, _request):
        raise RuntimeError("provider response contained a private detail")

    run = model_benchmark.run_benchmark(
        "owner:one",
        _suite(),
        [model_benchmark.ModelCandidate("ollama", "broken-model")],
        runner=runner,
    )
    results = model_benchmark.list_results("owner:one", run_id=run.run_id)

    assert run.status == "failed"
    assert run.success_count == 0
    assert run.failure_count == len(_suite().cases)
    assert all(item["error_code"] == "RuntimeError" for item in results)
    assert all(item["quality_score"] is None for item in results)
    assert "private detail" not in json.dumps(results)


def test_scorecards_require_minimum_measured_quality_samples_and_rank_models(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    suite = _suite()
    candidates = (
        model_benchmark.ModelCandidate("ollama", "accurate-model"),
        model_benchmark.ModelCandidate("ollama", "weak-model"),
    )

    def runner(candidate, request):
        prompt = request.to_messages()[-1]["content"]
        if candidate.model == "weak-model":
            return "incorrect"
        return {
            "Compute 2 + 2.": "4",
            "Classify a happy outcome.": "positive",
            "Reply with the word done.": "done",
        }[prompt]

    run = model_benchmark.run_benchmark(
        "owner:one", suite, candidates, runner=runner
    )
    # Repeated independent runs provide the minimum sample size.
    for _ in range(2):
        model_benchmark.run_benchmark(
            "owner:one", suite, candidates, runner=runner
        )

    cards = model_benchmark.scorecards(
        "owner:one",
        min_samples=3,
        min_quality_samples=3,
        target_latency_ms=1000,
    )
    by_model = {item.model: item for item in cards}

    assert by_model["accurate-model"].recommendation_eligible is True
    assert by_model["accurate-model"].average_quality_score == 1.0
    assert by_model["weak-model"].average_quality_score == 0.0
    assert by_model["accurate-model"].ranking_score > by_model["weak-model"].ranking_score
    assert cards[0].model == "accurate-model"


def test_runtime_metrics_apply_conservative_success_and_latency_floor(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    suite = _suite()
    candidate = model_benchmark.ModelCandidate("ollama", "measured-model")

    model_benchmark.run_benchmark(
        "owner:one",
        suite,
        [candidate],
        runner=lambda _candidate, _request: "4 positive done",
    )
    for latency, outcome in [(200, "success"), (300, "success"), (9000, "error")]:
        model_observability.record_event(
            scope="owner:one",
            provider="ollama",
            model="measured-model",
            route_reason="benchmark-test",
            latency_ms=latency,
            outcome=outcome,
        )

    card = model_benchmark.scorecards(
        "owner:one",
        min_samples=1,
        min_quality_samples=1,
        target_latency_ms=1000,
    )[0]

    assert card.runtime_request_count == 3
    assert card.runtime_success_rate == pytest.approx(2 / 3, abs=0.001)
    assert card.runtime_p95_latency_ms == 9000
    assert card.effective_success_rate == pytest.approx(2 / 3, abs=0.001)
    assert card.effective_p95_latency_ms == 9000
    assert card.latency_score == pytest.approx(1000 / 9000, abs=0.001)


def test_scorecards_keep_different_evaluators_separate(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    suite = _suite()
    candidate = model_benchmark.ModelCandidate("ollama", "same-model")

    model_benchmark.run_benchmark(
        "owner:one", suite, [candidate],
        runner=lambda _candidate, _request: "4 positive done",
    )
    model_benchmark.run_benchmark(
        "owner:one",
        model_benchmark.BenchmarkSuite(
            "custom-evaluator-suite",
            tuple(
                model_benchmark.BenchmarkCase(
                    f"custom-{index}",
                    "reasoning",
                    ({"role": "user", "content": f"case {index}"},),
                )
                for index in range(3)
            ),
        ),
        [candidate],
        runner=lambda _candidate, _request: "answer",
        quality_evaluator=lambda _case, answer: 0.75 if answer == "answer" else 0.0,
        quality_evaluator_id="manual_review_v1",
    )

    cards = model_benchmark.scorecards(
        "owner:one", min_samples=1, min_quality_samples=1
    )

    assert {item.evaluator_id for item in cards} == {
        "phrase_rubric_v1", "manual_review_v1"
    }
    assert len(cards) == 2


def test_suite_rejects_mixed_phrase_rubric_coverage():
    with pytest.raises(model_benchmark.ModelBenchmarkError, match="same built-in phrase-rubric"):
        model_benchmark.BenchmarkSuite(
            "mixed-rubric",
            (
                model_benchmark.BenchmarkCase(
                    "scored", "fast", ({"role": "user", "content": "x"},),
                    expected_contains=("x",),
                ),
                model_benchmark.BenchmarkCase(
                    "unscored", "fast", ({"role": "user", "content": "y"},)
                ),
            ),
        )


def test_benchmark_enforces_matrix_and_candidate_limits(monkeypatch, tmp_path):
    _use_db(monkeypatch, tmp_path)
    huge_suite = model_benchmark.BenchmarkSuite(
        "too-many",
        tuple(
            model_benchmark.BenchmarkCase(
                f"case-{i}", "fast", ({"role": "user", "content": "x"},),
                expected_contains=("x",),
            )
            for i in range(50)
        ),
    )
    candidates = [
        model_benchmark.ModelCandidate("ollama", f"model-{i}")
        for i in range(6)
    ]
    with pytest.raises(model_benchmark.ModelBenchmarkError, match="250-request"):
        model_benchmark.run_benchmark(
            "owner:one", huge_suite, candidates, runner=lambda _c, _r: "x"
        )
