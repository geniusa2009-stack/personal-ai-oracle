"""Explicit model benchmarking using measured latency, outcomes and bounded rubrics.

Prompts/completions are held in memory only. Persistence contains case IDs,
model labels, timing, outcome, output length and optional numeric rubric scores.
Hosted-provider calls are opt-in and no benchmark runs automatically.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from ai_request import AIRequest, Context
from database import init_database
from db import get_conn


DEFAULT_SUITE = Path(__file__).parent / "benchmarks" / "model_benchmark_cases.json"
MAX_CANDIDATES = 20
MAX_CASES = 50
MAX_REQUESTS = 250
MAX_SCOPE_LENGTH = 255
MAX_LABEL_LENGTH = 160
MAX_CASE_ID_LENGTH = 100
MAX_MESSAGE_CHARS = 20000
MAX_DB_RESULTS = 5000
DEFAULT_MIN_SAMPLES = 3
DEFAULT_MIN_QUALITY_SAMPLES = 3


class ModelBenchmarkError(ValueError):
    """Invalid benchmark suite, candidate, evaluator or report request."""


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model: str

    def __post_init__(self) -> None:
        provider = _label(self.provider, "provider", 80, r"[A-Za-z0-9_.-]+")
        model = _label(self.model, "model", MAX_LABEL_LENGTH, r"[A-Za-z0-9_./:-]+")
        object.__setattr__(self, "provider", provider.lower())
        object.__setattr__(self, "model", model)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    task_type: str
    messages: tuple[Mapping[str, Any], ...]
    temperature: float = 0.2
    expected_contains: tuple[str, ...] = ()
    forbidden_contains: tuple[str, ...] = ()
    response_format: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        case_id = _label(self.case_id, "case_id", MAX_CASE_ID_LENGTH, r"[A-Za-z0-9_.-]+")
        if not isinstance(self.task_type, str) or not self.task_type.strip() or len(self.task_type) > 80:
            raise ModelBenchmarkError("task_type is required and must be at most 80 characters")
        try:
            request = AIRequest(
                messages=tuple(self.messages),
                temperature=self.temperature,
                task_type=self.task_type.strip(),
                response_format=self.response_format,
            )
        except (TypeError, ValueError) as exc:
            raise ModelBenchmarkError(f"invalid benchmark request for case {case_id}") from exc
        message_chars = sum(
            len(str(message.get("content", "")))
            for message in request.to_messages()
        )
        if message_chars > MAX_MESSAGE_CHARS:
            raise ModelBenchmarkError(f"case {case_id} exceeds the message size limit")
        expected = _phrases(self.expected_contains, "expected_contains")
        forbidden = _phrases(self.forbidden_contains, "forbidden_contains")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "task_type", self.task_type.strip())
        object.__setattr__(self, "messages", request.messages)
        object.__setattr__(self, "temperature", float(self.temperature))
        object.__setattr__(self, "expected_contains", expected)
        object.__setattr__(self, "forbidden_contains", forbidden)
        if self.response_format is not None:
            object.__setattr__(self, "response_format", request.response_format)


@dataclass(frozen=True)
class BenchmarkSuite:
    suite_id: str
    cases: tuple[BenchmarkCase, ...]

    def __post_init__(self) -> None:
        suite_id = _label(self.suite_id, "suite_id", 100, r"[A-Za-z0-9_.-]+")
        cases = tuple(self.cases)
        if not cases or len(cases) > MAX_CASES:
            raise ModelBenchmarkError(f"a suite must contain between 1 and {MAX_CASES} cases")
        ids = [case.case_id for case in cases]
        if len(set(ids)) != len(ids):
            raise ModelBenchmarkError("benchmark case IDs must be unique")
        object.__setattr__(self, "suite_id", suite_id)
        object.__setattr__(self, "cases", cases)


@dataclass(frozen=True)
class BenchmarkRun:
    run_id: str
    scope: str
    suite_id: str
    status: str
    candidate_count: int
    case_count: int
    request_count: int
    success_count: int
    failure_count: int
    allow_remote: bool
    created_at: str
    finished_at: str | None


@dataclass(frozen=True)
class ModelScorecard:
    provider: str
    model: str
    sample_count: int
    success_rate: float
    quality_sample_count: int
    quality_coverage: float
    average_quality_score: float | None
    benchmark_p50_latency_ms: int
    benchmark_p95_latency_ms: int
    runtime_request_count: int
    runtime_success_rate: float | None
    runtime_p95_latency_ms: int | None
    effective_success_rate: float
    effective_p95_latency_ms: int
    latency_score: float
    ranking_score: float | None
    recommendation_eligible: bool
    eligibility_reason: str


Runner = Callable[[ModelCandidate, AIRequest], str]
QualityEvaluator = Callable[[BenchmarkCase, str], float]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_SCOPE_LENGTH:
        raise ModelBenchmarkError("scope is required and must be at most 255 characters")
    return value.strip()


def _label(value: Any, field: str, maximum: int, pattern: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ModelBenchmarkError(f"{field} is required and must be at most {maximum} characters")
    value = value.strip()
    if not re.fullmatch(pattern, value):
        raise ModelBenchmarkError(f"{field} contains unsupported characters")
    return value


def _phrases(values: Sequence[str], field: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > 20:
        raise ModelBenchmarkError(f"{field} must contain at most 20 phrases")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value) > 300:
            raise ModelBenchmarkError(f"{field} contains an invalid phrase")
        normalized.append(value.strip())
    return tuple(normalized)


def _normalise_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _rubric_score(case: BenchmarkCase, answer: str) -> tuple[float | None, str | None]:
    """Deterministic phrase checks only; this is not semantic answer verification."""
    if not case.expected_contains and not case.forbidden_contains:
        return None, None
    normalized = _normalise_text(answer)
    checks = [
        phrase in normalized for phrase in case.expected_contains
    ] + [
        phrase not in normalized for phrase in case.forbidden_contains
    ]
    if not checks:
        return None, None
    return sum(checks) / len(checks), "phrase_rubric_v1"


def _is_loopback_ollama() -> bool:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    try:
        host = (urlparse(base_url).hostname or "").casefold()
    except ValueError:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


def _default_runner_factory() -> Runner:
    import ai_core

    executors: dict[str, Any] = {}

    def run(candidate: ModelCandidate, request: AIRequest) -> str:
        executor = executors.get(candidate.provider)
        if executor is None:
            executor = ai_core._multi_executor(provider_name=candidate.provider)
            executors[candidate.provider] = executor
        return executor.execute(request).content

    return run


def load_suite(path: str | Path = DEFAULT_SUITE) -> BenchmarkSuite:
    """Load the bundled synthetic suite; prompts are never copied into result tables."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelBenchmarkError("unable to load model benchmark suite") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ModelBenchmarkError("unsupported model benchmark suite schema")
    cases_data = payload.get("cases")
    if not isinstance(cases_data, list) or not cases_data:
        raise ModelBenchmarkError("model benchmark suite must contain cases")
    cases = []
    for entry in cases_data:
        if not isinstance(entry, dict):
            raise ModelBenchmarkError("every benchmark case must be an object")
        cases.append(BenchmarkCase(
            case_id=entry.get("id"),
            task_type=entry.get("task_type"),
            messages=tuple(entry.get("messages", ())),
            temperature=entry.get("temperature", 0.2),
            expected_contains=tuple(entry.get("expected_contains", ())),
            forbidden_contains=tuple(entry.get("forbidden_contains", ())),
            response_format=entry.get("response_format"),
        ))
    return BenchmarkSuite(str(payload.get("suite_id", "custom")), tuple(cases))


def _persist_result(
    *,
    run_id: str,
    scope: str,
    candidate: ModelCandidate,
    case: BenchmarkCase,
    latency_ms: int,
    outcome: str,
    output_chars: int,
    quality_score: float | None,
    evaluator_id: str | None,
    error_code: str | None,
    evaluation_error_code: str | None,
    created_at: str,
) -> None:
    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO oracle_model_benchmark_results
               (run_id,scope,provider,model,case_id,task_type,latency_ms,outcome,
                output_chars,quality_score,evaluator_id,error_code,
                evaluation_error_code,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, scope, candidate.provider, candidate.model, case.case_id,
                case.task_type, latency_ms, outcome, output_chars, quality_score,
                evaluator_id, error_code, evaluation_error_code, created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def run_benchmark(
    scope: str,
    suite: BenchmarkSuite,
    candidates: Sequence[ModelCandidate],
    *,
    runner: Runner | None = None,
    quality_evaluator: QualityEvaluator | None = None,
    quality_evaluator_id: str | None = None,
    allow_remote: bool = False,
) -> BenchmarkRun:
    """Run an explicit candidate-by-case matrix and store only numeric outcomes.

    By default, only a loopback Ollama endpoint is allowed. Hosted providers
    require allow_remote=True, acknowledging potential charges and transfer of
    the synthetic benchmark messages. Injected runners are used for offline tests.
    """
    scope = _scope(scope)
    if not isinstance(suite, BenchmarkSuite):
        raise ModelBenchmarkError("suite must be a BenchmarkSuite")
    if not isinstance(candidates, (list, tuple)) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ModelBenchmarkError(f"candidates must contain 1 to {MAX_CANDIDATES} models")
    if not isinstance(allow_remote, bool):
        raise ModelBenchmarkError("allow_remote must be a boolean")

    normalized_candidates = tuple(candidates)
    if any(not isinstance(item, ModelCandidate) for item in normalized_candidates):
        raise ModelBenchmarkError("every candidate must be a ModelCandidate")
    identities = [(item.provider, item.model) for item in normalized_candidates]
    if len(set(identities)) != len(identities):
        raise ModelBenchmarkError("candidate provider/model pairs must be unique")
    request_count = len(normalized_candidates) * len(suite.cases)
    if request_count > MAX_REQUESTS:
        raise ModelBenchmarkError(f"benchmark exceeds the {MAX_REQUESTS}-request safety limit")

    remote_candidates = [
        item for item in normalized_candidates
        if item.provider != "ollama" or not _is_loopback_ollama()
    ]
    if remote_candidates and not allow_remote:
        labels = ", ".join(f"{item.provider}/{item.model}" for item in remote_candidates)
        raise ModelBenchmarkError(
            f"hosted or non-loopback candidates require allow_remote=True: {labels}"
        )

    evaluator_id = None
    if quality_evaluator is not None:
        evaluator_id = _label(
            quality_evaluator_id, "quality_evaluator_id", 100, r"[A-Za-z0-9_.-]+"
        )
    elif any(case.expected_contains or case.forbidden_contains for case in suite.cases):
        evaluator_id = "phrase_rubric_v1"

    selected_runner = runner or _default_runner_factory()
    run_id = uuid.uuid4().hex
    created_at = _now()
    init_database()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO oracle_model_benchmark_runs
               (run_id,scope,suite_id,status,candidate_count,case_count,request_count,
                success_count,failure_count,allow_remote,evaluator_id,created_at,finished_at)
               VALUES(?,?,?,'running',?,?,?,0,0,?,?,?,NULL)""",
            (
                run_id, scope, suite.suite_id, len(normalized_candidates),
                len(suite.cases), request_count, int(allow_remote), evaluator_id, created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    successes = 0
    failures = 0
    completed = 0
    try:
        for candidate in normalized_candidates:
            for case in suite.cases:
                request = AIRequest(
                    messages=case.messages,
                    temperature=case.temperature,
                    requested_model=candidate.model,
                    requested_provider=candidate.provider,
                    task_type=case.task_type,
                    response_format=case.response_format,
                    context=Context(metadata={
                        "owner_scope": scope,
                        "benchmark": True,
                        "benchmark_run_id": run_id,
                    }),
                )
                started = time.monotonic()
                outcome = "error"
                output_chars = 0
                score = None
                row_evaluator_id = evaluator_id
                error_code = None
                evaluation_error_code = None
                try:
                    answer = selected_runner(candidate, request)
                    if not isinstance(answer, str):
                        raise TypeError("benchmark runner must return text")
                    output_chars = len(answer)
                    outcome = "success"
                    successes += 1
                    try:
                        if quality_evaluator is not None:
                            score = float(quality_evaluator(case, answer))
                            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                                raise ValueError("quality evaluator must return a finite score from 0 to 1")
                        else:
                            score, _ = _rubric_score(case, answer)
                        if score is None:
                            row_evaluator_id = None
                    except Exception as exc:
                        score = None
                        evaluation_error_code = type(exc).__name__
                        row_evaluator_id = evaluator_id
                except Exception as exc:
                    outcome = "error"
                    error_code = type(exc).__name__
                    failures += 1
                latency_ms = max(0, int((time.monotonic() - started) * 1000))
                _persist_result(
                    run_id=run_id,
                    scope=scope,
                    candidate=candidate,
                    case=case,
                    latency_ms=latency_ms,
                    outcome=outcome,
                    output_chars=output_chars,
                    quality_score=score,
                    evaluator_id=row_evaluator_id,
                    error_code=error_code,
                    evaluation_error_code=evaluation_error_code,
                    created_at=_now(),
                )
                completed += 1
    except Exception:
        status = "partial" if completed else "failed"
        _finish_run(run_id, scope, status, successes, failures)
        raise

    status = "completed" if failures == 0 else ("failed" if successes == 0 else "partial")
    _finish_run(run_id, scope, status, successes, failures)
    return get_run(scope, run_id)  # type: ignore[return-value]


def _finish_run(run_id: str, scope: str, status: str, successes: int, failures: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE oracle_model_benchmark_runs
               SET status=?,success_count=?,failure_count=?,finished_at=?
               WHERE run_id=? AND scope=?""",
            (status, successes, failures, _now(), run_id, scope),
        )
        conn.commit()
    finally:
        conn.close()


def get_run(scope: str, run_id: str) -> BenchmarkRun | None:
    scope = _scope(scope)
    run_id = _label(run_id, "run_id", 64, r"[A-Fa-f0-9]+")
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT run_id,scope,suite_id,status,candidate_count,case_count,request_count,
                      success_count,failure_count,allow_remote,created_at,finished_at
               FROM oracle_model_benchmark_runs WHERE run_id=? AND scope=?""",
            (run_id, scope),
        ).fetchone()
        if row is None:
            return None
        return BenchmarkRun(
            run_id=row["run_id"], scope=row["scope"], suite_id=row["suite_id"],
            status=row["status"], candidate_count=int(row["candidate_count"]),
            case_count=int(row["case_count"]), request_count=int(row["request_count"]),
            success_count=int(row["success_count"]), failure_count=int(row["failure_count"]),
            allow_remote=bool(row["allow_remote"]), created_at=row["created_at"],
            finished_at=row["finished_at"],
        )
    finally:
        conn.close()


def list_results(
    scope: str,
    *,
    run_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    scope = _scope(scope)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ModelBenchmarkError("limit must be an integer from 1 to 1000")
    params: list[Any] = [scope]
    where = "scope=?"
    if run_id is not None:
        run_id = _label(run_id, "run_id", 64, r"[A-Fa-f0-9]+")
        where += " AND run_id=?"
        params.append(run_id)
    params.append(limit)
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT run_id,provider,model,case_id,task_type,latency_ms,outcome,
                      output_chars,quality_score,evaluator_id,error_code,
                      evaluation_error_code,created_at
               FROM oracle_model_benchmark_results WHERE """
            + where
            + " ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def scorecards(
    scope: str,
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_quality_samples: int = DEFAULT_MIN_QUALITY_SAMPLES,
    target_latency_ms: int = 3000,
    quality_weight: float = 0.65,
    success_weight: float = 0.20,
    latency_weight: float = 0.15,
    limit: int = MAX_DB_RESULTS,
) -> list[ModelScorecard]:
    """Rank models only when measured rubric and sample evidence meet thresholds.

    Live model_observability metrics add a conservative health floor: effective
    success is the lower of benchmark/runtime success, and effective p95 latency
    is the higher observed p95. No cost is inferred.
    """
    scope = _scope(scope)
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 1:
        raise ModelBenchmarkError("min_samples must be a positive integer")
    if isinstance(min_quality_samples, bool) or not isinstance(min_quality_samples, int) or min_quality_samples < 1:
        raise ModelBenchmarkError("min_quality_samples must be a positive integer")
    if isinstance(target_latency_ms, bool) or not isinstance(target_latency_ms, int) or target_latency_ms < 1:
        raise ModelBenchmarkError("target_latency_ms must be a positive integer")
    weights = (quality_weight, success_weight, latency_weight)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
        for value in weights
    ) or not math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ModelBenchmarkError("ranking weights must be finite values from 0 to 1 and sum to 1")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_DB_RESULTS:
        raise ModelBenchmarkError(f"limit must be between 1 and {MAX_DB_RESULTS}")

    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT r.provider,r.model,r.latency_ms,r.outcome,r.quality_score
               FROM oracle_model_benchmark_results AS r
               JOIN oracle_model_benchmark_runs AS b
                 ON b.run_id=r.run_id AND b.scope=r.scope
               WHERE r.scope=? AND b.status IN ('completed','partial')
               ORDER BY r.id DESC LIMIT ?""",
            (scope, limit),
        ).fetchall()
    finally:
        conn.close()

    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in rows:
        groups[(row["provider"], row["model"])].append(row)

    runtime = {}
    try:
        import model_observability
        runtime = {
            (item["provider"], item["model"]): item
            for item in model_observability.summary(scope, limit=1000)
        }
    except Exception:
        runtime = {}

    results = []
    for (provider, model), items in groups.items():
        latencies = [int(item["latency_ms"]) for item in items]
        successes = sum(item["outcome"] == "success" for item in items)
        quality_values = [
            float(item["quality_score"])
            for item in items if item["quality_score"] is not None
        ]
        sample_count = len(items)
        quality_count = len(quality_values)
        benchmark_success = successes / sample_count
        quality_average = sum(quality_values) / quality_count if quality_count else None
        benchmark_p50 = _percentile(latencies, 0.50)
        benchmark_p95 = _percentile(latencies, 0.95)
        runtime_item = runtime.get((provider, model))
        runtime_requests = int(runtime_item["requests"]) if runtime_item else 0
        runtime_success = float(runtime_item["success_rate"]) if runtime_item else None
        runtime_p95 = int(runtime_item["p95_latency_ms"]) if runtime_item else None
        effective_success = (
            min(benchmark_success, runtime_success)
            if runtime_requests >= min_samples and runtime_success is not None
            else benchmark_success
        )
        effective_p95 = max(benchmark_p95, runtime_p95 or 0)
        latency_score = min(1.0, target_latency_ms / max(1, effective_p95))
        eligible = sample_count >= min_samples and quality_count >= min_quality_samples
        if eligible and quality_average is not None:
            ranking = (
                quality_weight * quality_average
                + success_weight * effective_success
                + latency_weight * latency_score
            )
            reason = "eligible: sufficient measured samples and rubric coverage"
        else:
            ranking = None
            reason = (
                f"requires {min_samples} samples and {min_quality_samples} scored cases; "
                f"observed {sample_count} samples and {quality_count} scored cases"
            )
        results.append(ModelScorecard(
            provider=provider, model=model, sample_count=sample_count,
            success_rate=round(benchmark_success, 4),
            quality_sample_count=quality_count,
            quality_coverage=round(quality_count / sample_count, 4),
            average_quality_score=round(quality_average, 4) if quality_average is not None else None,
            benchmark_p50_latency_ms=benchmark_p50,
            benchmark_p95_latency_ms=benchmark_p95,
            runtime_request_count=runtime_requests,
            runtime_success_rate=round(runtime_success, 4) if runtime_success is not None else None,
            runtime_p95_latency_ms=runtime_p95,
            effective_success_rate=round(effective_success, 4),
            effective_p95_latency_ms=effective_p95,
            latency_score=round(latency_score, 4),
            ranking_score=round(ranking, 4) if ranking is not None else None,
            recommendation_eligible=eligible,
            eligibility_reason=reason,
        ))
    return sorted(
        results,
        key=lambda item: (
            item.recommendation_eligible,
            item.ranking_score if item.ranking_score is not None else -1.0,
            item.average_quality_score if item.average_quality_score is not None else -1.0,
            item.effective_success_rate,
            -item.effective_p95_latency_ms,
        ),
        reverse=True,
    )
