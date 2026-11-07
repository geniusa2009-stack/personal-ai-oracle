"""Domain-aware freshness policies for Personal AI Oracle research sources.

Policies are configurable starting guardrails, not universal truth. The general
profile is deliberately unassessed unless the caller selects a domain or a
conservative query classifier recognizes a time-sensitive category.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

import evidence_verification


@dataclass(frozen=True)
class FreshnessPolicy:
    profile: str
    max_age_days: int | None
    description: str


POLICIES: dict[str, FreshnessPolicy] = {
    "general": FreshnessPolicy(
        "general", None,
        "No universal freshness threshold is applied to general research.",
    ),
    "scholarship_deadline": FreshnessPolicy(
        "scholarship_deadline", 30,
        "Starting guardrail for application and scholarship deadline research.",
    ),
    "event_schedule": FreshnessPolicy(
        "event_schedule", 14,
        "Starting guardrail for event dates, schedules, and registration information.",
    ),
    "pricing": FreshnessPolicy(
        "pricing", 7,
        "Starting guardrail for prices, fees, subscriptions, and commercial offers.",
    ),
    "government_policy": FreshnessPolicy(
        "government_policy", 90,
        "Starting guardrail for current government policies and regulatory information.",
    ),
    "software_api": FreshnessPolicy(
        "software_api", 180,
        "Starting guardrail for software APIs, SDKs, and product documentation.",
    ),
    "scientific_research": FreshnessPolicy(
        "scientific_research", 730,
        "Starting guardrail for scientific studies and research summaries.",
    ),
}

# Narrow, explicit query hints. This is classification assistance, not an
# authoritative understanding of the user's intent.
QUERY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scholarship_deadline", (
        "scholarship", "scholarships", "grant", "grants", "application deadline",
        "deadline", "منحة", "منح", "آخر موعد", "موعد التقديم",
    )),
    ("event_schedule", (
        "event", "events", "conference", "conferences", "schedule", "registration",
        "ticket", "فعالية", "فعاليات", "مؤتمر", "مؤتمرات", "جدول الفعاليات",
    )),
    ("pricing", (
        "price", "prices", "pricing", "cost", "fee", "fees", "subscription",
        "السعر", "الأسعار", "تكلفة", "رسوم", "اشتراك",
    )),
    ("government_policy", (
        "law", "laws", "regulation", "regulations", "government policy", "policy",
        "قانون", "قوانين", "لائحة", "لوائح", "سياسة حكومية", "قرار حكومي",
    )),
    ("software_api", (
        "api", "sdk", "software documentation", "api documentation", "release notes",
        "version compatibility", "توثيق api", "توثيق البرمجيات", "إصدار البرنامج",
    )),
    ("scientific_research", (
        "scientific study", "research paper", "clinical trial", "systematic review",
        "دراسة علمية", "بحث علمي", "تجربة سريرية", "مراجعة منهجية",
    )),
)


class FreshnessPolicyError(ValueError):
    """Raised for unknown freshness policy names or invalid inputs."""


def available_profiles() -> list[dict[str, Any]]:
    """Return the supported profiles and their current configured thresholds."""
    return [
        {
            "profile": item.profile,
            "max_age_days": item.max_age_days,
            "description": item.description,
        }
        for item in POLICIES.values()
    ]


def _matches_hint(query: str, hint: str) -> bool:
    normalized_hint = " ".join(hint.casefold().split())
    if " " in normalized_hint:
        return normalized_hint in query
    return re.search(
        rf"(?<![\\w]){re.escape(normalized_hint)}(?![\\w])",
        query,
        flags=re.UNICODE,
    ) is not None


def resolve_policy(
    query: str,
    *,
    requested_profile: str | None = None,
) -> dict[str, Any]:
    """Resolve an explicit policy or a narrow query-derived policy.

    An unrecognized/general query resolves to the general profile with no
    expiry threshold. It is never silently assigned an arbitrary age.
    """
    if not isinstance(query, str):
        raise FreshnessPolicyError("query must be text")
    if requested_profile is not None:
        if not isinstance(requested_profile, str) or requested_profile not in POLICIES:
            raise FreshnessPolicyError(
                "requested_profile must be one of: " + ", ".join(POLICIES)
            )
        selected = POLICIES[requested_profile]
        source = "explicit"
        matched_hint = None
    else:
        normalized = " ".join(query.casefold().split())
        selected = POLICIES["general"]
        matched_hint = None
        for profile, hints in QUERY_HINTS:
            matched = next((hint for hint in hints if _matches_hint(normalized, hint)), None)
            if matched:
                selected = POLICIES[profile]
                matched_hint = matched
                break
        source = "query_hint" if matched_hint else "default_unassessed"

    return {
        "profile": selected.profile,
        "max_age_days": selected.max_age_days,
        "policy_source": source,
        "matched_hint": matched_hint,
        "description": selected.description,
    }


def assess_sources(
    sources: Sequence[Mapping[str, Any]],
    query: str,
    *,
    requested_profile: str | None = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Assess source freshness using a resolved domain policy.

    The supplied sources must already carry normalized publication/update dates.
    Retrieval and extraction timestamps are preserved but never used as the
    freshness reference.
    """
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        raise FreshnessPolicyError("sources must be a sequence")
    policy = resolve_policy(query, requested_profile=requested_profile)
    assessments = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        freshness = evidence_verification.assess_source_freshness(
            source,
            max_age_days=policy["max_age_days"],
            as_of=as_of,
        )
        assessments.append({
            "citation_id": str(source.get("citation_id") or "")[:32],
            "status": freshness["status"],
            "reference_date": freshness["reference_date"],
            "reference_kind": freshness["reference_kind"],
            "age_days": freshness["age_days"],
            "max_age_days": freshness["max_age_days"],
            "policy_profile": policy["profile"],
        })

    counts = {
        status: sum(item["status"] == status for item in assessments)
        for status in ("fresh", "stale", "unknown", "future_dated", "not_assessed")
    }
    return {
        **policy,
        "assessed_source_count": len(assessments),
        "counts": counts,
        "results": assessments,
        "limitations": [
            "Freshness is a policy comparison against source publication/update metadata, not proof that the source is accurate.",
            "Search-provider and page-extractor date hints may be missing or inaccurate.",
            "General research is not assigned a universal freshness threshold.",
        ],
    }
