import pytest

from app.analytics.guideline_gaps import (
    cluster_dismissal_reasons,
    summarize_rule_decisions,
    validate_suggestion_payload,
)


def test_cluster_dismissal_reasons_is_deterministic_and_groups_similar_feedback():
    reasons = [
        "Too vague for our style guide",
        "The guideline is too vague",
        "Not relevant to our brand",
        "Not relevant for our brand",
    ]

    first = cluster_dismissal_reasons(reasons)
    second = cluster_dismissal_reasons(reversed(reasons))

    assert first == second
    assert len(first) == 2
    assert sorted(cluster["count"] for cluster in first) == [2, 2]
    assert all(cluster["qualifies"] for cluster in first)


def test_cluster_dismissal_reasons_bounds_examples_and_ignores_empty_values():
    reasons = ["same reason"] * 8 + ["", "  ", None]
    clusters = cluster_dismissal_reasons(reasons)

    assert len(clusters) == 1
    assert clusters[0]["count"] == 8
    assert len(clusters[0]["examples"]) == 5


def test_summarize_rule_decisions_uses_decided_denominator_and_gap_threshold():
    rows = [
        {"action": "dismiss", "reason": "Too vague for our brand", "source_version": 1},
        {"action": "dismiss", "reason": "The wording is too vague", "source_version": 1},
        {"action": "dismiss", "reason": "Too vague for our style guide", "source_version": 2},
        {"action": "dismiss", "reason": "Wording is too vague", "source_version": 2},
        {"action": "accept", "reason": None, "source_version": 2},
    ]

    result = summarize_rule_decisions(rows)

    assert result["decided"] == 5
    assert result["dismissed"] == 4
    assert result["acted_on"] == 1
    assert result["dismissal_rate"] == 0.8
    assert result["source_versions"] == [1, 2]
    assert result["is_gap"] is True


def test_summarize_rule_decisions_does_not_flag_insufficient_sample():
    rows = [
        {"action": "dismiss", "reason": "Too vague for our brand", "source_version": 1},
        {"action": "dismiss", "reason": "The wording is too vague", "source_version": 1},
    ]

    result = summarize_rule_decisions(rows)

    assert result["decided"] == 2
    assert result["is_gap"] is False


def test_validate_suggestion_payload_rejects_missing_or_unchanged_text():
    with pytest.raises(ValueError):
        validate_suggestion_payload({"explanation": "Clearer"}, "Original rule")

    with pytest.raises(ValueError):
        validate_suggestion_payload(
            {"suggested_text": "Original rule", "explanation": "Clearer"},
            "Original rule",
        )


def test_validate_suggestion_payload_accepts_bounded_output():
    result = validate_suggestion_payload(
        {
            "suggested_text": "Use plain language and define technical terms on first use.",
            "explanation": "Clarifies the expectation without changing its intent.",
        },
        "Use clear language.",
    )

    assert result[0].startswith("Use plain language")


def test_unclustered_reasons_are_grouped_as_other_without_qualifying_as_a_gap():
    reasons = [
        "Budget is unclear",
        "Seasonality is missing",
        "This is not our audience",
        "Need a source link",
        "The tone is too formal",
    ]

    clusters = cluster_dismissal_reasons(reasons)

    assert len(clusters) == 1
    assert clusters[0]["theme"] == "Other"
    assert clusters[0]["count"] == 5
    assert clusters[0]["qualifies"] is False

    decisions = [
        {"action": "dismiss", "reason": reason, "source_version": 1}
        for reason in reasons
    ]
    assert summarize_rule_decisions(decisions)["is_gap"] is False
