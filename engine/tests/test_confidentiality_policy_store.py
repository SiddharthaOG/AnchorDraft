"""Tests for organization-scoped confidentiality policy loading."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.confidentiality import ConfidentialityPolicyStore


ORG_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_missing_policy_uses_safe_builtin_defaults():
    supabase = MagicMock()
    supabase.get_confidentiality_policy.return_value = None

    policy = await ConfidentialityPolicyStore(supabase).load_policy(ORG_ID)

    assert policy.org_id == ORG_ID
    assert policy.enabled is True
    assert policy.redact_emails is True
    assert policy.redact_phones is True
    assert policy.redact_api_keys is True
    assert policy.redact_jwts is True
    assert policy.redact_credit_cards is True
    assert policy.custom_terms == ()


@pytest.mark.asyncio
async def test_policy_is_loaded_for_requested_org_and_terms_are_normalized():
    supabase = MagicMock()
    supabase.get_confidentiality_policy.return_value = {
        "org_id": str(ORG_ID),
        "version": 7,
        "enabled": True,
        "custom_terms": ["  Project Apollo ", "", "Client X"],
        "redact_emails": True,
        "redact_phones": False,
        "redact_api_keys": True,
        "redact_jwts": True,
        "redact_credit_cards": False,
    }

    policy = await ConfidentialityPolicyStore(supabase).load_policy(ORG_ID)

    supabase.get_confidentiality_policy.assert_called_once_with(str(ORG_ID))
    assert policy.version == 7
    assert policy.custom_terms == ("Project Apollo", "Client X")
    assert policy.redact_phones is False
    assert policy.redact_credit_cards is False


@pytest.mark.asyncio
async def test_cross_org_policy_record_fails_closed():
    supabase = MagicMock()
    supabase.get_confidentiality_policy.return_value = {
        "org_id": "22222222-2222-2222-2222-222222222222",
        "version": 1,
        "custom_terms": [],
    }

    with pytest.raises(ValueError, match="organization mismatch"):
        await ConfidentialityPolicyStore(supabase).load_policy(ORG_ID)


@pytest.mark.asyncio
async def test_malformed_policy_terms_fail_closed():
    supabase = MagicMock()
    supabase.get_confidentiality_policy.return_value = {
        "org_id": str(ORG_ID),
        "version": 1,
        "custom_terms": "not-an-array",
    }

    with pytest.raises(ValueError, match="custom_terms is invalid"):
        await ConfidentialityPolicyStore(supabase).load_policy(ORG_ID)


@pytest.mark.asyncio
async def test_policy_database_error_is_not_swallowed():
    supabase = MagicMock()
    supabase.get_confidentiality_policy.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await ConfidentialityPolicyStore(supabase).load_policy(ORG_ID)


def test_supabase_client_scopes_policy_query_to_exact_org():
    from app.auth.supabase import SupabaseClient

    client = SupabaseClient()
    mock_client = MagicMock()
    response = MagicMock()
    expected = {"org_id": str(ORG_ID), "version": 1, "custom_terms": []}
    response.data = [expected]
    query = mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value
    query.execute.return_value = response

    client._client = mock_client
    assert client.get_confidentiality_policy(str(ORG_ID)) == expected
    mock_client.table.assert_called_once_with("confidentiality_policies")
    mock_client.table.return_value.select.assert_called_once_with("*")
    mock_client.table.return_value.select.return_value.eq.assert_called_once_with("org_id", str(ORG_ID))
