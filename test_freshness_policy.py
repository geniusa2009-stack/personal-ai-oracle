import pytest

import freshness_policy


def _source(source_id="S1", **overrides):
    value = {
        "citation_id": source_id,
        "published_at": "2026-01-01",
        "updated_at": None,
        "retrieved_at": "2026-11-07T00:00:00Z",
        "extracted_at": "2026-11-07T00:05:00Z",
    }
    value.update(overrides)
    return value


def test_general_queries_remain_unassessed_instead_of_using_universal_threshold():
    policy = freshness_policy.resolve_policy("Explain how photosynthesis works")

    assert policy["profile"] == "general"
    assert policy["max_age_days"] is None
    assert policy["policy_source"] == "default_unassessed"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Find current scholarships for students", "scholarship_deadline"),
        ("What are the prices and monthly cost?", "pricing"),
        ("Upcoming conference schedule", "event_schedule"),
        ("Recent government policy regulation", "government_policy"),
        ("Latest API documentation and SDK version", "software_api"),
        ("Find a clinical trial research paper", "scientific_research"),
    ],
)
def test_query_hints_resolve_domain_specific_profiles(query, expected):
    policy = freshness_policy.resolve_policy(query)

    assert policy["profile"] == expected
    assert policy["policy_source"] == "query_hint"
    assert policy["max_age_days"] is not None


def test_keyword_matching_avoids_substring_false_positive():
    policy = freshness_policy.resolve_policy("How does a coffee machine work?")

    assert policy["profile"] == "general"


def test_explicit_profile_overrides_query_hint():
    policy = freshness_policy.resolve_policy(
        "Find scholarship deadlines",
        requested_profile="pricing",
    )

    assert policy["profile"] == "pricing"
    assert policy["policy_source"] == "explicit"
    assert policy["matched_hint"] is None


def test_unknown_explicit_profile_is_rejected():
    with pytest.raises(freshness_policy.FreshnessPolicyError):
        freshness_policy.resolve_policy("Research", requested_profile="daily")


def test_assess_sources_uses_publication_update_dates_not_retrieval_dates():
    report = freshness_policy.assess_sources(
        [
            _source("S1", published_at="2026-01-01"),
            _source("S2", published_at=None, updated_at="2026-11-01"),
            _source("S3", published_at=None, updated_at=None),
        ],
        "scholarship deadline",
        as_of="2026-11-07T00:00:00Z",
    )

    assert report["profile"] == "scholarship_deadline"
    assert report["counts"] == {
        "fresh": 1,
        "stale": 1,
        "unknown": 1,
        "future_dated": 0,
        "not_assessed": 0,
    }
    assert report["results"][0]["status"] == "stale"
    assert report["results"][0]["reference_kind"] == "published_at"
    assert report["results"][1]["status"] == "fresh"
    assert report["results"][1]["reference_kind"] == "updated_at"
    assert report["results"][2]["status"] == "unknown"


def test_general_profile_does_not_assess_freshness():
    report = freshness_policy.assess_sources(
        [_source()],
        "Explain a stable mathematical concept",
        as_of="2026-11-07T00:00:00Z",
    )

    assert report["profile"] == "general"
    assert report["counts"]["not_assessed"] == 1
    assert report["results"][0]["status"] == "not_assessed"


def test_assess_sources_rejects_non_sequence_input():
    with pytest.raises(freshness_policy.FreshnessPolicyError):
        freshness_policy.assess_sources("not sources", "pricing")
