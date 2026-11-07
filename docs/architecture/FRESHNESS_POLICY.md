# Domain-Aware Research Freshness Policy

**Implementation branch:** `oracle/phase-01-temporal-evidence`  
**Parent:** PR #6 — semantic claim verification.

## Purpose

This increment adds a policy-driven freshness assessment to Deep Research. It compares a source's publisher/update date metadata with a configurable age threshold.

Freshness is not factual accuracy, source authority, or proof that a document is still in force. An old source can remain authoritative for historical research; a newly updated source can still be incorrect.

## Timestamp semantics

The source record keeps these values separate:

- `published_at`: publication date hint.
- `updated_at`: last-updated date hint.
- `retrieved_at`: when Oracle received the search result.
- `extracted_at`: when Oracle extracted the page.

Freshness assessment uses `updated_at` when available, otherwise `published_at`. It does **not** use retrieval or extraction time as a proxy for content age.

Invalid or missing publication/update metadata yields `unknown` for policies with an age threshold. Future dates yield `future_dated` and a warning.

## Profiles and initial thresholds

These are configurable starting guardrails, not universal facts:

| Profile | Initial maximum age | Typical use |
|---|---:|---|
| `general` | No threshold | General explanations and stable topics |
| `scholarship_deadline` | 30 days | Scholarship and application deadlines |
| `event_schedule` | 14 days | Event schedules and registration |
| `pricing` | 7 days | Prices, fees, and subscriptions |
| `government_policy` | 90 days | Current policies and regulatory information |
| `software_api` | 180 days | APIs, SDKs, software documentation |
| `scientific_research` | 730 days | Scientific papers and research summaries |

The `general` profile deliberately has no default expiry threshold. Oracle must not label every older source stale regardless of the subject.

## Policy selection

Deep Research accepts an optional `freshness_profile` input to select a profile explicitly.

When no profile is supplied, a conservative bilingual keyword classifier chooses a profile for a small set of time-sensitive query categories. Otherwise it selects `general` and reports `not_assessed`.

The selected profile is returned with its policy source:

- `explicit`
- `query_hint`
- `default_unassessed`

Automatic query classification is a hint-based heuristic. It should not override explicit user instructions or be treated as a full understanding of the research intent.

## Freshness statuses

- `fresh`: within the selected age threshold.
- `stale`: older than the selected threshold.
- `unknown`: age threshold is active but no valid publication/update date exists.
- `future_dated`: the chosen publication/update date is in the future relative to the assessment time.
- `not_assessed`: no age threshold applies, including the default general profile.

A `stale` result is a prompt to verify the current primary source; it does not prove that the information is false.

## Deep Research integration

Each source and citation receives a bounded `freshness` object. The research report includes:

- `freshness_assessment.profile`
- `freshness_assessment.policy_source`
- `freshness_assessment.max_age_days`
- `freshness_assessment.counts`
- `freshness_assessment.results[]`
- `evidence_summary.freshness_profile`
- `evidence_summary.freshness_policy_source`
- `evidence_summary.freshness_max_age_days`
- `evidence_summary.freshness_counts`

When sources are stale, date metadata is unknown under an active policy, or source dates are future-dated, the report records a limitation and may return `partial` status.

The compact report preserves a bounded freshness summary and per-source statuses for planner/tool history.

## Known limitations

- The starting thresholds need calibration against real usage and may need per-country or per-source overrides.
- Search and page extractors may provide missing or inaccurate date hints.
- Date metadata origin is preserved, but this increment does not prove that the publisher supplied or cryptographically verified the date.
- It does not determine whether a policy or deadline has been superseded by a new official document.
- It does not resolve contradictions between two sources.
- It does not persist immutable page snapshots.
- The query classifier is intentionally narrow and can choose general when a query is ambiguous.

## Next steps

1. Support explicit per-request and per-domain configuration from application settings.
2. Add publisher-specific and jurisdiction-specific freshness rules where justified.
3. Integrate temporal validity and structured contradiction candidates into a reviewable source-comparison report.
4. Build a human-reviewed bilingual benchmark to measure stale-detection false positives and false negatives.
