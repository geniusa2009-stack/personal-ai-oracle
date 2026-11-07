"""Structured evidence and claim metadata for Personal AI Oracle.

This module establishes a deterministic evidence contract. It deliberately does
not claim semantic entailment or factual truth: candidate claims remain UNVERIFIED
until a separately evaluated verifier has assessed the supplied evidence.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


_CITATION_RE = re.compile(r"\[(S[1-9][0-9]*)\]")
_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?؟])\s+|\n+")
_SOURCE_ID_RE = re.compile(r"^S[1-9][0-9]*$")
_MAX_CLAIMS = 80
_MAX_SOURCE_TEXT = 2000
_MAX_METADATA_TEXT = 500


class EvidenceError(ValueError):
    """Raised when evidence or claim metadata violates the contract."""


def _text(value: Any, maximum: int = _MAX_METADATA_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()[:maximum]


def _timestamp(value: Any) -> str | None:
    """Normalize ISO date/time values to UTC; return None for unknown/invalid dates."""
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    elif isinstance(value, str) and value.strip():
        candidate = value.strip()
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            try:
                date_value = date.fromisoformat(candidate)
                parsed = datetime(
                    date_value.year, date_value.month, date_value.day,
                    tzinfo=timezone.utc,
                )
            except ValueError:
                return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _safe_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ""
        if parsed.username or parsed.password:
            return ""
        return value.strip()
    except ValueError:
        return ""


def normalize_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a research source into a bounded, explicit provenance record."""
    if not isinstance(source, Mapping):
        raise EvidenceError("source must be a mapping")

    source_id = source.get("citation_id") or source.get("id")
    if not isinstance(source_id, str) or not _SOURCE_ID_RE.fullmatch(source_id):
        raise EvidenceError("source requires a valid S-number citation_id")

    page_status = _text(source.get("page_status"), 80) or "unknown"
    snippet = _text(source.get("snippet"), _MAX_SOURCE_TEXT)
    title = _text(source.get("title"), 300)
    url = _safe_url(source.get("url"))
    domain = _text(source.get("domain"), 180)
    publisher = _text(source.get("publisher"), 180) or domain

    if page_status == "extracted":
        evidence_level = "extracted_page"
    elif page_status == "not_fetched":
        evidence_level = "search_snippet_only" if snippet else "no_content"
    elif page_status in {"unknown", ""}:
        evidence_level = "unknown"
    else:
        evidence_level = "unavailable_or_partial"

    return {
        "citation_id": source_id,
        "title": title,
        "url": url,
        "publisher": publisher,
        "domain": domain,
        "source_class": _text(source.get("source_class"), 80) or "unknown",
        "page_status": page_status,
        "evidence_level": evidence_level,
        "snippet": snippet,
        "published_at": _timestamp(source.get("published_at")),
        "updated_at": _timestamp(source.get("updated_at")),
        "retrieved_at": _timestamp(source.get("retrieved_at")),
        "extracted_at": _timestamp(source.get("extracted_at")),
        "date_metadata_origin": _text(source.get("date_metadata_origin"), 80) or "search_or_extractor_unverified",
    }


def normalize_sources(sources: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        raise EvidenceError("sources must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        try:
            item = normalize_source(source)
        except EvidenceError:
            continue
        if item["citation_id"] in seen:
            continue
        seen.add(item["citation_id"])
        normalized.append(item)
    return normalized


def assess_source_freshness(
    source: Mapping[str, Any],
    *,
    max_age_days: int | None,
    as_of: datetime | date | str | None = None,
) -> dict[str, Any]:
    """Evaluate source-date freshness without treating retrieval time as publication."""
    if max_age_days is not None and (
        isinstance(max_age_days, bool)
        or not isinstance(max_age_days, int)
        or not 1 <= max_age_days <= 36500
    ):
        raise EvidenceError("max_age_days must be an integer from 1 to 36500 or None")

    published = _timestamp(source.get("published_at"))
    updated = _timestamp(source.get("updated_at"))
    reference_value = updated or published
    reference_kind = "updated_at" if updated else ("published_at" if published else None)
    if max_age_days is None:
        return {
            "status": "not_assessed",
            "reference_date": reference_value,
            "reference_kind": reference_kind,
            "age_days": None,
            "max_age_days": None,
        }
    if reference_value is None:
        return {
            "status": "unknown",
            "reference_date": None,
            "reference_kind": None,
            "age_days": None,
            "max_age_days": max_age_days,
        }

    current = _timestamp(as_of) if as_of is not None else datetime.now(timezone.utc).isoformat(timespec="seconds")
    current_dt = datetime.fromisoformat(current.replace("Z", "+00:00"))
    reference_dt = datetime.fromisoformat(reference_value.replace("Z", "+00:00"))
    age_seconds = (current_dt - reference_dt).total_seconds()
    if age_seconds < 0:
        status = "future_dated"
        age_days = round(age_seconds / 86400, 2)
    else:
        age_days = round(age_seconds / 86400, 2)
        status = "stale" if age_days > max_age_days else "fresh"

    return {
        "status": status,
        "reference_date": reference_value,
        "reference_kind": reference_kind,
        "age_days": age_days,
        "max_age_days": max_age_days,
    }


def build_claim_candidates(
    answer: str,
    sources: list[Mapping[str, Any]],
    *,
    max_claims: int = _MAX_CLAIMS,
) -> list[dict[str, Any]]:
    """Build sentence-level candidates; do not imply atomic claim extraction."""
    if not isinstance(answer, str):
        raise EvidenceError("answer must be text")
    if isinstance(max_claims, bool) or not isinstance(max_claims, int) or not 1 <= max_claims <= 200:
        raise EvidenceError("max_claims must be an integer from 1 to 200")

    source_records = normalize_sources(list(sources))
    source_by_id = {item["citation_id"]: item for item in source_records}
    candidates: list[dict[str, Any]] = []
    for chunk in _CLAIM_SPLIT_RE.split(answer.strip()):
        claim_text = chunk.strip(" \t•-*")
        if not claim_text:
            continue
        mentioned = list(dict.fromkeys(_CITATION_RE.findall(claim_text)))
        valid_ids = [item for item in mentioned if item in source_by_id]
        invalid_ids = [item for item in mentioned if item not in source_by_id]
        evidence = [
            {
                "citation_id": source_id,
                "evidence_level": source_by_id[source_id]["evidence_level"],
                "page_status": source_by_id[source_id]["page_status"],
                "url": source_by_id[source_id]["url"],
                "published_at": source_by_id[source_id]["published_at"],
                "updated_at": source_by_id[source_id]["updated_at"],
            }
            for source_id in valid_ids[:6]
        ]
        candidates.append({
            "claim_id": f"C{len(candidates) + 1}",
            "text": claim_text[:700],
            "claim_type": "unclassified",
            "granularity": "sentence_level_candidate",
            "source_ids": valid_ids[:6],
            "invalid_source_ids": invalid_ids[:6],
            "citation_status": (
                "invalid_reference" if invalid_ids
                else "citation_present" if valid_ids
                else "uncited"
            ),
            "verification_status": "UNVERIFIED",
            "semantic_support": "not_evaluated",
            "evidence": evidence,
        })
        if len(candidates) >= max_claims:
            break
    return candidates


def _normal_key(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def _interval(value: Mapping[str, Any]) -> tuple[datetime | None, datetime | None, bool]:
    start_raw = value.get("valid_from")
    end_raw = value.get("valid_until")
    start = _timestamp(start_raw)
    end = _timestamp(end_raw)
    invalid = bool(start_raw and not start) or bool(end_raw and not end)
    return (
        datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None,
        datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None,
        invalid,
    )


def _temporal_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> str:
    left_start, left_end, left_invalid = _interval(left)
    right_start, right_end, right_invalid = _interval(right)
    if left_invalid or right_invalid:
        return "unknown"
    start_values = [value for value in (left_start, right_start) if value is not None]
    end_values = [value for value in (left_end, right_end) if value is not None]
    start = max(start_values) if start_values else None
    end = min(end_values) if end_values else None
    if start is not None and end is not None and start > end:
        return "disjoint"
    if all(value is not None for value in (left_start, left_end, right_start, right_end)):
        return "overlap"
    return "unknown"


def detect_structured_contradictions(claims: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Flag potential conflicts only for explicitly structured claim tuples.

    This deterministic check is a candidate generator, not semantic contradiction
    proof. It never guesses subject/predicate/object from natural-language text.
    """
    if not isinstance(claims, list):
        raise EvidenceError("claims must be a list")

    prepared = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            continue
        subject = _normal_key(claim.get("subject"))
        predicate = _normal_key(claim.get("predicate"))
        object_value = _normal_key(claim.get("object"))
        if not subject or not predicate or not object_value:
            continue
        prepared.append({
            "claim_id": _text(claim.get("claim_id"), 80) or f"C{index + 1}",
            "subject": subject,
            "predicate": predicate,
            "object": object_value,
            "source_ids": [
                item for item in claim.get("source_ids", [])
                if isinstance(item, str) and _SOURCE_ID_RE.fullmatch(item)
            ][:8] if isinstance(claim.get("source_ids", []), list) else [],
            "valid_from": claim.get("valid_from"),
            "valid_until": claim.get("valid_until"),
        })

    conflicts = []
    for index, left in enumerate(prepared):
        for right in prepared[index + 1:]:
            if left["subject"] != right["subject"] or left["predicate"] != right["predicate"]:
                continue
            if left["object"] == right["object"]:
                continue
            overlap = _temporal_overlap(left, right)
            if overlap == "disjoint":
                continue
            conflicts.append({
                "conflict_id": f"X{len(conflicts) + 1}",
                "claim_ids": [left["claim_id"], right["claim_id"]],
                "source_ids": list(dict.fromkeys(left["source_ids"] + right["source_ids"])),
                "subject": left["subject"],
                "predicate": left["predicate"],
                "values": [left["object"], right["object"]],
                "temporal_overlap": overlap,
                "status": "POTENTIAL_CONTRADICTION",
                "requires_review": True,
                "explanation": (
                    "Structured claims share a subject and predicate but specify different values. "
                    "This is a potential conflict, not a semantic contradiction verdict."
                ),
            })
    return conflicts
