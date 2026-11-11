"""Tests for confidentiality detection, replacement, and reverse mapping."""

from uuid import UUID

from app.confidentiality import (
    ConfidentialityEngine,
    ConfidentialityPolicy,
    expand_placeholders,
)


ORG_ID = UUID("11111111-1111-1111-1111-111111111111")


def policy(**overrides):
    values = {"org_id": ORG_ID, "custom_terms": ("Project Apollo", "Client X")}
    values.update(overrides)
    return ConfidentialityPolicy(**values)


def test_redacts_custom_terms_case_insensitively_and_prefers_longest_overlap():
    engine = ConfidentialityEngine()
    source = "The PROJECT APOLLO launch includes Client X."
    result = engine.redact(source, policy())

    assert "PROJECT APOLLO" not in result.redacted_text
    assert "Client X" not in result.redacted_text
    assert len(result.matches) == 2
    assert result.summary.by_type == {"custom_term": 2}
    assert result.summary.original_chars == len(source)
    assert result.summary.redacted_chars == len(result.redacted_text)


def test_redacts_email_phone_api_key_jwt_and_luhn_valid_card():
    engine = ConfidentialityEngine()
    values = [
        "person@example.com",
        "+1 (415) 555-2671",
        "sk_live_12345678901234567890",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature1234567890",
        "4111 1111 1111 1111",
    ]
    source = " | ".join(values)
    result = engine.redact(source, policy(custom_terms=()))

    for value in values:
        assert value not in result.redacted_text
    assert result.summary.total_matches == 5
    assert result.summary.by_type == {
        "email": 1,
        "phone": 1,
        "api_key": 1,
        "jwt": 1,
        "credit_card": 1,
    }


def test_repeated_sensitive_values_get_unique_placeholders_and_expand_exactly():
    engine = ConfidentialityEngine()
    source = "Contact person@example.com or person@example.com."
    result = engine.redact(source, policy(custom_terms=()))

    placeholders = [match.placeholder for match in result.matches]
    assert len(placeholders) == 2
    assert len(set(placeholders)) == 2
    assert expand_placeholders(result.redacted_text, result.placeholder_map) == source


def test_unicode_offsets_are_mapped_to_original_text():
    engine = ConfidentialityEngine()
    source = "🔥 Client X is the confidential project."
    result = engine.redact(source, policy(custom_terms=("Client X",)))

    match = result.matches[0]
    assert source[match.start:match.end] == "Client X"
    assert result.redacted_text.startswith("🔥 ")


def test_disabled_policy_returns_original_text_without_matches():
    source = "person@example.com"
    result = ConfidentialityEngine().redact(
        source,
        policy(enabled=False, custom_terms=()),
    )

    assert result.redacted_text == source
    assert result.matches == ()
    assert result.placeholder_map == {}


def test_redact_fields_uses_one_reverse_map_across_prompt_fields():
    engine = ConfidentialityEngine()
    fields = {
        "draft": "Send to person@example.com",
        "purpose": "Reach person@example.com",
        "channel": "email",
    }
    result = engine.redact_fields(fields, policy(custom_terms=()))

    assert result.summary.total_matches == 2
    assert len(result.placeholder_map) == 2
    for name, original in fields.items():
        assert expand_placeholders(result.fields[name], result.placeholder_map) == original
    assert "person@example.com" not in " ".join(result.fields.values())


def test_summary_does_not_contain_sensitive_source_values():
    secret = "person@example.com"
    result = ConfidentialityEngine().redact(secret, policy(custom_terms=()))

    assert secret not in repr(result.summary)
    assert secret not in repr(result.summary.by_type)
