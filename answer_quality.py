"""Deterministic, conservative quality signals for evidence-based answers.

This module measures citation integrity and evidence availability. It does NOT
claim that a cited source semantically supports a claim; that requires an
independent entailment check and, ultimately, domain validation.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_CITATION_RE = re.compile(r"\[(S[1-9][0-9]*)\]")
_SPLIT_RE = re.compile(r"(?<=[.!?؟])\s+|\n+")
_SOURCE_ID_RE = re.compile(r"S[1-9][0-9]*")


def _claims(answer: str, maximum: int) -> list[str]:
    return [
        item.strip(" \t•-*")
        for item in _SPLIT_RE.split(answer.strip())
        if item.strip(" \t•-*")
    ][:maximum]


def assess_claim_citations(
    answer: str,
    sources: Iterable[dict[str, Any]],
    *,
    max_claims: int = 80,
) -> dict[str, Any]:
    """Assess citation presence and source availability without overstating support."""
    if not isinstance(answer, str):
        raise ValueError("answer must be text")
    if isinstance(max_claims, bool) or not isinstance(max_claims, int) or not 1 <= max_claims <= 200:
        raise ValueError("max_claims must be an integer from 1 to 200")

    source_map: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("citation_id")
        if isinstance(source_id, str) and _SOURCE_ID_RE.fullmatch(source_id):
            source_map[source_id] = source

    claims: list[dict[str, Any]] = []
    for text in _claims(answer, max_claims):
        mentioned = list(dict.fromkeys(_CITATION_RE.findall(text)))
        valid = [item for item in mentioned if item in source_map]
        invalid = [item for item in mentioned if item not in source_map]
        if invalid:
            status = "invalid_reference"
        elif not valid:
            status = "uncited"
        else:
            status = "citation_present_unverified"

        source_details = []
        for source_id in valid[:6]:
            source = source_map[source_id]
            page_status = str(source.get("page_status") or "unknown")
            source_details.append({
                "source_id": source_id,
                "page_status": page_status,
                "evidence_level": (
                    "extracted_page" if page_status == "extracted"
                    else "search_snippet_only" if page_status == "not_fetched"
                    else "unavailable_or_partial"
                ),
            })
        claims.append({
            "claim": text[:700],
            "source_ids": valid[:6],
            "invalid_source_ids": invalid[:6],
            "citation_status": status,
            "semantic_support": "not_evaluated",
            "sources": source_details,
        })

    total = len(claims)
    cited = sum(bool(item["source_ids"]) for item in claims)
    any_reference = sum(bool(item["source_ids"] or item["invalid_source_ids"]) for item in claims)
    uncited = sum(item["citation_status"] == "uncited" for item in claims)
    invalid = sum(item["citation_status"] == "invalid_reference" for item in claims)
    extracted = sum(
        detail["evidence_level"] == "extracted_page"
        for item in claims for detail in item["sources"]
    )
    snippet_only = sum(
        detail["evidence_level"] == "search_snippet_only"
        for item in claims for detail in item["sources"]
    )
    coverage = round(cited / total, 4) if total else 0.0

    if total == 0:
        status = "no_claims_detected"
    elif uncited or invalid:
        status = "needs_citation_review"
    else:
        status = "citations_present_semantics_unverified"

    return {
        "status": status,
        "assessment_scope": "citation_integrity_and_source_availability_only",
        "semantic_entailment_checked": False,
        "truth_verified": False,
        "claim_count": total,
        "claims_with_citations": cited,
        "claims_with_any_reference": any_reference,
        "uncited_claim_count": uncited,
        "invalid_reference_claim_count": invalid,
        "citation_coverage": coverage,
        "extracted_page_references": extracted,
        "snippet_only_references": snippet_only,
        "claims": claims,
        "limitations": [
            "A citation being present does not prove that its source supports the claim.",
            "Source authority, freshness, and factual truth are not established by this assessment.",
        ],
    }
