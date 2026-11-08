"""Explicit, one-shot submission and dispatch for bounded Deep Research tasks.

This module connects the durable queue to one allowlisted, read-only research
handler. It never starts a worker, scheduler, daemon, or background service.
"""

from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.parse import urlsplit

import deep_research
import durable_task_engine
import freshness_policy
import task_worker


TASK_TYPE_RESEARCH = "oracle.deep_research"
MAX_STORED_RESULT_BYTES = 32_000
_ALLOWED_FRESHNESS_PROFILES = frozenset({
    "general",
    "scholarship_deadline",
    "event_schedule",
    "pricing",
    "government_policy",
    "software_api",
    "scientific_research",
})


class TaskExecutionError(ValueError):
    """Invalid task submission, handler payload, or stored research result."""


class ResearchTaskFailed(RuntimeError):
    """Deep Research returned no usable source set."""


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TaskExecutionError(f"{field} must be text")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise TaskExecutionError(f"{field} must contain 1 to {maximum} characters")
    return normalized


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise TaskExecutionError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _submission_payload(
    query: Any,
    *,
    max_queries: Any,
    max_sources: Any,
    fetch_pages: Any,
    verify_claims: Any,
    freshness_profile: Any,
) -> dict[str, Any]:
    normalized_query = _text(query, "query", deep_research.MAX_QUERY_LENGTH)
    queries = _bounded_int(max_queries, "max_queries", 1, deep_research.MAX_QUERIES)
    sources = _bounded_int(max_sources, "max_sources", 1, deep_research.MAX_SOURCES)
    if not isinstance(fetch_pages, bool) or not isinstance(verify_claims, bool):
        raise TaskExecutionError("fetch_pages and verify_claims must be booleans")
    if freshness_profile is not None:
        if not isinstance(freshness_profile, str) or freshness_profile not in _ALLOWED_FRESHNESS_PROFILES:
            raise TaskExecutionError("freshness_profile is unsupported")
        try:
            freshness_policy.resolve_policy(
                normalized_query,
                requested_profile=freshness_profile,
            )
        except freshness_policy.FreshnessPolicyError as exc:
            raise TaskExecutionError("freshness_profile is invalid") from exc
    return {
        "query": normalized_query,
        "max_queries": queries,
        "max_sources": sources,
        "fetch_pages": fetch_pages,
        "verify_claims": verify_claims,
        "freshness_profile": freshness_profile,
    }


def create_research_graph(
    scope: str,
    idempotency_key: str,
    query: str,
    *,
    max_queries: int = 3,
    max_sources: int = 8,
    fetch_pages: bool = True,
    verify_claims: bool = True,
    freshness_profile: str | None = None,
) -> durable_task_engine.TaskGraph:
    """Persist one encrypted, non-retryable Deep Research task in the owner scope."""
    payload = _submission_payload(
        query,
        max_queries=max_queries,
        max_sources=max_sources,
        fetch_pages=fetch_pages,
        verify_claims=verify_claims,
        freshness_profile=freshness_profile,
    )
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise TaskExecutionError("idempotency_key is required")
    return durable_task_engine.create_graph(
        scope,
        idempotency_key,
        [
            durable_task_engine.TaskSpec(
                task_key="research",
                task_type=TASK_TYPE_RESEARCH,
                payload=payload,
                max_attempts=1,
                retry_safe=False,
            )
        ],
    )


def _safe_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Keep a useful, bounded evidence summary; omit full page bodies and raw prompts."""
    citations = []
    for item in report.get("citations", [])[:8]:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        citations.append({
            "id": str(item.get("id") or "")[:12],
            "title": str(item.get("title") or "")[:240],
            "url": url[:2048],
            "domain": str(item.get("domain") or "")[:160],
            "publisher": str(item.get("publisher") or "")[:160],
            "published_at": str(item.get("published_at") or "")[:100],
            "updated_at": str(item.get("updated_at") or "")[:100],
        })

    sources = []
    for item in report.get("sources", [])[:8]:
        if not isinstance(item, Mapping):
            continue
        sources.append({
            "citation_id": str(item.get("citation_id") or "")[:12],
            "title": str(item.get("title") or "")[:240],
            "domain": str(item.get("domain") or "")[:160],
            "page_status": str(item.get("page_status") or "")[:40],
            "evidence_excerpt": str(item.get("evidence_excerpt") or "")[:350],
            "evidence_level": str(item.get("evidence_level") or "")[:40],
        })

    semantic = report.get("semantic_verification", {})
    if not isinstance(semantic, Mapping):
        semantic = {}
    freshness = report.get("freshness_assessment", {})
    if not isinstance(freshness, Mapping):
        freshness = {}
    evidence = report.get("evidence_summary", {})
    if not isinstance(evidence, Mapping):
        evidence = {}
    quality = report.get("quality_assessment", {})
    if not isinstance(quality, Mapping):
        quality = {}

    result = {
        "kind": "research_report",
        "status": str(report.get("status") or "partial")[:20],
        "query": str(report.get("query") or "")[:deep_research.MAX_QUERY_LENGTH],
        "answer": str(report.get("answer") or "")[:4200],
        "key_findings": [str(item)[:350] for item in report.get("key_findings", [])[:6]],
        "limitations": [str(item)[:350] for item in report.get("limitations", [])[:8]],
        "citations": citations,
        "sources": sources,
        "evidence_summary": {
            key: evidence.get(key)
            for key in (
                "source_count", "extracted_page_count", "snippet_only_count",
                "unavailable_or_partial_count", "claim_candidate_count",
                "semantic_verification", "freshness_profile",
                "freshness_policy_source", "freshness_max_age_days",
                "freshness_counts",
            )
            if key in evidence
        },
        "quality_summary": {
            key: quality.get(key)
            for key in (
                "status", "assessment_scope", "semantic_entailment_checked",
                "truth_verified", "claim_count", "citation_coverage",
                "uncited_claim_count", "invalid_reference_claim_count",
            )
            if key in quality
        },
        "semantic_summary": {
            "status": str(semantic.get("status") or "not_performed")[:30],
            "semantic_entailment_checked": semantic.get("semantic_entailment_checked") is True,
            "factual_truth_verified": False,
            "checked_claim_count": semantic.get("checked_claim_count", 0),
            "unverified_claim_count": semantic.get("unverified_claim_count", 0),
        },
        "freshness_summary": {
            "profile": str(freshness.get("profile") or "general")[:40],
            "policy_source": str(freshness.get("policy_source") or "unknown")[:40],
            "max_age_days": freshness.get("max_age_days"),
            "counts": freshness.get("counts", {}),
        },
    }
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_STORED_RESULT_BYTES:
        result["answer"] = result["answer"][:2400]
        result["key_findings"] = result["key_findings"][:4]
        result["limitations"] = result["limitations"][:5]
        result["citations"] = result["citations"][:5]
        result["sources"] = result["sources"][:5]
        for source in result["sources"]:
            source["evidence_excerpt"] = source["evidence_excerpt"][:180]
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_STORED_RESULT_BYTES:
        raise TaskExecutionError("bounded research result exceeds the storage budget")
    return result


def _research_handler(
    payload: Mapping[str, Any],
    context: task_worker.TaskExecutionContext,
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise TaskExecutionError("research task payload must be an object")
    allowed = {
        "query", "max_queries", "max_sources", "fetch_pages",
        "verify_claims", "freshness_profile",
    }
    if set(payload) != allowed:
        raise TaskExecutionError("research task payload has missing or unknown fields")
    normalized = _submission_payload(
        payload["query"],
        max_queries=payload["max_queries"],
        max_sources=payload["max_sources"],
        fetch_pages=payload["fetch_pages"],
        verify_claims=payload["verify_claims"],
        freshness_profile=payload["freshness_profile"],
    )
    if context.cancellation_requested():
        raise ResearchTaskFailed("task was cancelled before research started")
    report = deep_research.run_research(
        normalized["query"],
        memory_scope=context.scope,
        max_queries=normalized["max_queries"],
        max_sources=normalized["max_sources"],
        fetch_pages=normalized["fetch_pages"],
        verify_claims=normalized["verify_claims"],
        freshness_profile=normalized["freshness_profile"],
        max_correction_retries=1,
    )
    if not isinstance(report, Mapping):
        raise TaskExecutionError("research engine returned an invalid report")
    if report.get("status") == "error":
        raise ResearchTaskFailed("research returned no usable sources")
    if context.cancellation_requested():
        raise ResearchTaskFailed("task was cancelled before result persistence")
    return _safe_report(report)


def dispatch_research_once(
    scope: str,
    worker_id: str,
    *,
    lease_seconds: int = 120,
) -> task_worker.TaskDispatchResult | None:
    """Run at most one queued research task; no polling or background activation."""
    return task_worker.dispatch_once(
        scope,
        worker_id,
        {
            TASK_TYPE_RESEARCH: task_worker.TaskHandler(
                execute=_research_handler,
                retryable_exceptions=(),
            )
        },
        lease_seconds=lease_seconds,
    )


def get_research_result(scope: str, task_id: str) -> dict[str, Any] | None:
    """Return an allowlisted owner-scope result preview, never encrypted/raw payloads."""
    task = durable_task_engine.get_task(scope, task_id, include_result=True)
    if task is None or task.get("task_type") != TASK_TYPE_RESEARCH:
        return None
    if task.get("status") != "succeeded":
        return None
    stored = task.get("result")
    if not isinstance(stored, Mapping) or stored.get("kind") != "research_report":
        raise TaskExecutionError("stored research result is malformed")
    # Re-project the stored value to a strict UI contract; never trust arbitrary keys.
    evidence = stored.get("evidence_summary", {})
    quality = stored.get("quality_summary", {})
    semantic = stored.get("semantic_summary", {})
    freshness = stored.get("freshness_summary", {})
    evidence = evidence if isinstance(evidence, Mapping) else {}
    quality = quality if isinstance(quality, Mapping) else {}
    semantic = semantic if isinstance(semantic, Mapping) else {}
    freshness = freshness if isinstance(freshness, Mapping) else {}

    citations = []
    for item in stored.get("citations", [])[:8]:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        citations.append({
            "id": str(item.get("id") or "")[:12],
            "title": str(item.get("title") or "")[:240],
            "url": url[:2048],
            "domain": str(item.get("domain") or "")[:160],
        })

    return {
        "status": str(stored.get("status") or "partial")[:20],
        "query": str(stored.get("query") or "")[:deep_research.MAX_QUERY_LENGTH],
        "answer": str(stored.get("answer") or "")[:4200],
        "key_findings": [
            str(item)[:350] for item in stored.get("key_findings", [])[:6]
        ] if isinstance(stored.get("key_findings", []), list) else [],
        "limitations": [
            str(item)[:350] for item in stored.get("limitations", [])[:8]
        ] if isinstance(stored.get("limitations", []), list) else [],
        "citations": citations,
        "evidence_summary": {
            key: evidence[key]
            for key in (
                "source_count", "extracted_page_count", "snippet_only_count",
                "unavailable_or_partial_count", "claim_candidate_count",
                "semantic_verification", "freshness_profile",
                "freshness_policy_source", "freshness_max_age_days",
                "freshness_counts",
            )
            if key in evidence
        },
        "quality_summary": {
            key: quality[key]
            for key in (
                "status", "assessment_scope", "semantic_entailment_checked",
                "truth_verified", "claim_count", "citation_coverage",
                "uncited_claim_count", "invalid_reference_claim_count",
            )
            if key in quality
        },
        "semantic_summary": {
            "status": str(semantic.get("status") or "not_performed")[:30],
            "semantic_entailment_checked": semantic.get("semantic_entailment_checked") is True,
            "factual_truth_verified": False,
            "checked_claim_count": semantic.get("checked_claim_count", 0),
            "unverified_claim_count": semantic.get("unverified_claim_count", 0),
        },
        "freshness_summary": {
            "profile": str(freshness.get("profile") or "general")[:40],
            "policy_source": str(freshness.get("policy_source") or "unknown")[:40],
            "max_age_days": freshness.get("max_age_days"),
            "counts": freshness.get("counts", {}) if isinstance(freshness.get("counts", {}), Mapping) else {},
        },
    }
