"""Tests for owner-managed organization confidentiality policy API."""
import pytest
from pydantic import ValidationError

from app.api.confidentiality import ConfidentialityPolicyUpdate, _safe_policy


def test_policy_update_accepts_custom_terms_and_builtin_toggles():
    payload = ConfidentialityPolicyUpdate(
        enabled=True,
        custom_terms=["ORCHID-VAULT-ALPHA", "Internal Project"],
        redact_emails=True,
        redact_phones=False,
    )
    assert payload.custom_terms == ["ORCHID-VAULT-ALPHA", "Internal Project"]
    assert payload.redact_phones is False


@pytest.mark.parametrize("terms", [
    [""],
    ["   "],
    ["duplicate", "DUPLICATE"],
    ["x" * 257],
])
def test_policy_update_rejects_invalid_custom_terms(terms):
    with pytest.raises(ValidationError):
        ConfidentialityPolicyUpdate(custom_terms=terms)


def test_policy_update_rejects_more_than_500_terms():
    with pytest.raises(ValidationError):
        ConfidentialityPolicyUpdate(custom_terms=[f"term-{i}" for i in range(501)])


def test_policy_update_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ConfidentialityPolicyUpdate(custom_terms=[], org_id="another-org")


def test_safe_policy_does_not_expose_database_metadata():
    record = {
        "id": "policy-id",
        "org_id": "11111111-1111-1111-1111-111111111111",
        "version": 3,
        "enabled": True,
        "custom_terms": ["Internal Project"],
        "redact_emails": True,
        "redact_phones": True,
        "redact_api_keys": True,
        "redact_jwts": True,
        "redact_credit_cards": True,
        "updated_by": "user-id",
        "created_at": "now",
    }
    result = _safe_policy(record, record["org_id"])
    assert result["custom_terms"] == ["Internal Project"]
    assert "updated_by" not in result
    assert "id" not in result
