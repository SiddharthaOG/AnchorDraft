"""Tests for SupabaseClient methods."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4, UUID

from app.auth.supabase import SupabaseClient


class TestSupabaseClientGetKit:
    """Tests for SupabaseClient.get_kit method."""

    @pytest.fixture
    def mock_supabase_client(self):
        """Create a SupabaseClient with mocked internal client."""
        with patch.object(SupabaseClient, '_get_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            client = SupabaseClient()
            yield client, mock_client

    def test_get_kit_existing(self, mock_supabase_client):
        """Test get_kit returns the expected record for an existing kit."""
        client, mock_client = mock_supabase_client
        
        kit_id = str(uuid4())
        expected_kit = {
            "id": kit_id,
            "org_id": "org-123",
            "name": "Test Kit",
            "status": "active",
            "version": 1,
        }
        
        # Mock the table chain
        mock_execute = MagicMock()
        mock_execute.data = [expected_kit]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute
        
        result = client.get_kit(kit_id)
        
        assert result == expected_kit
        mock_client.table.assert_called_once_with("brand_kits")
        mock_client.table.return_value.select.assert_called_once_with("*")
        mock_client.table.return_value.select.return_value.eq.assert_called_once_with("id", kit_id)

    def test_get_kit_missing(self, mock_supabase_client):
        """Test get_kit returns None for a nonexistent kit."""
        client, mock_client = mock_supabase_client
        
        kit_id = str(uuid4())
        
        mock_execute = MagicMock()
        mock_execute.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_execute
        
        result = client.get_kit(kit_id)
        
        assert result is None

    def test_get_kit_database_error(self, mock_supabase_client):
        """Test get_kit propagates database exceptions."""
        client, mock_client = mock_supabase_client
        
        kit_id = str(uuid4())
        
        mock_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception, match="Connection failed"):
            client.get_kit(kit_id)


class TestKitLintEndpointAuthorization:
    """Tests for kit lint endpoint organization isolation."""

    @pytest.fixture
    def mock_supabase(self):
        """Create a fully mocked SupabaseClient."""
        with patch('app.api.kits.get_supabase_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def auth_user(self):
        """Create a mock authenticated user."""
        from app.auth.dependencies import AuthUser
        return AuthUser(
            user_id="user-123",
            org_id="org-123",
            roles=["owner"]
        )

    @pytest.mark.asyncio
    async def test_lint_kit_cross_org_rejected(self, mock_supabase, auth_user):
        """Test that lint endpoint rejects a kit belonging to another organization."""
        from app.api.kits import lint_kit
        from uuid import UUID
        from fastapi import HTTPException
        
        kit_id = UUID("11111111-1111-1111-1111-111111111111")
        
        # Kit belongs to a different organization
        mock_supabase.get_kit.return_value = {
            "id": str(kit_id),
            "org_id": "org-999",  # Different org
            "name": "Other Org Kit",
            "status": "active",
            "version": 1,
        }
        
        # Should raise 404 (not 403, to avoid leaking existence)
        with pytest.raises(HTTPException) as exc_info:
            await lint_kit(kit_id=kit_id, user=auth_user)
        
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Kit not found"

    @pytest.mark.asyncio
    async def test_lint_kit_same_org_allowed(self, mock_supabase, auth_user):
        """Test that lint endpoint allows access to own organization's kit."""
        from app.api.kits import lint_kit
        from uuid import UUID
        
        kit_id = UUID("11111111-1111-1111-1111-111111111111")
        
        # Kit belongs to the same organization
        mock_supabase.get_kit.return_value = {
            "id": str(kit_id),
            "org_id": "org-123",  # Same org as user
            "name": "My Kit",
            "status": "active",
            "version": 1,
        }
        mock_supabase.get_kit_rules.return_value = []
        mock_supabase.get_kit_facts.return_value = []
        
        # Should not raise - just returns the lint result
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        assert "ok" in result
        assert "issues" in result
        assert "stats" in result
        assert "warnings" in result

    @pytest.mark.asyncio
    async def test_lint_kit_nonexistent(self, mock_supabase, auth_user):
        """Test that lint endpoint returns 404 for nonexistent kit."""
        from app.api.kits import lint_kit
        from uuid import UUID
        from fastapi import HTTPException
        
        kit_id = UUID("11111111-1111-1111-1111-111111111111")
        
        mock_supabase.get_kit.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await lint_kit(kit_id=kit_id, user=auth_user)
        
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Kit not found"


class TestKitLintEndpointWarnings:
    """Tests for lint endpoint warnings field."""

    @pytest.fixture
    def mock_supabase(self):
        """Create a fully mocked SupabaseClient."""
        with patch('app.api.kits.get_supabase_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def auth_user(self):
        """Create a mock authenticated user."""
        from app.auth.dependencies import AuthUser
        return AuthUser(
            user_id="user-123",
            org_id="org-123",
            roles=["owner"]
        )

    @pytest.fixture
    def kit_id(self):
        return UUID("11111111-1111-1111-1111-111111111111")

    @pytest.mark.asyncio
    async def test_lint_warnings_empty_list_when_no_warnings(self, mock_supabase, auth_user, kit_id):
        """Test that warnings field is an empty list when no warnings exist."""
        from app.api.kits import lint_kit
        
        mock_supabase.get_kit.return_value = {
            "id": str(kit_id),
            "org_id": "org-123",
            "name": "My Kit",
            "status": "active",
            "version": 1,
        }
        mock_supabase.get_kit_rules.return_value = [
            {
                "rule_key": "RULE-01",
                "category": "terminology",
                "severity": "medium",
                "title": "Test Rule",
                "guideline_text": "Test guideline",
                "check_kind": "deterministic",
                "config": {"check": "phrase_list", "phrases": ["bad phrase"]},
                "needs_reviewer": False,
            }
        ]
        mock_supabase.get_kit_facts.return_value = []
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        assert "warnings" in result
        assert isinstance(result["warnings"], list)
        assert result["warnings"] == []

    @pytest.mark.asyncio
    async def test_lint_warnings_contains_expired_fact_warning(self, mock_supabase, auth_user, kit_id):
        """Test that warnings contains expired fact warning."""
        from app.api.kits import lint_kit
        from datetime import date, timedelta
        
        mock_supabase.get_kit.return_value = {
            "id": str(kit_id),
            "org_id": "org-123",
            "name": "My Kit",
            "status": "active",
            "version": 1,
        }
        mock_supabase.get_kit_rules.return_value = []
        # Fact with past valid_until date
        past_date = (date.today() - timedelta(days=1)).isoformat()
        mock_supabase.get_kit_facts.return_value = [
            {
                "fact_key": "FACT-01",
                "statement": "Test fact",
                "source_note": "Test source",
                "valid_until": past_date,
            }
        ]
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        assert "warnings" in result
        assert len(result["warnings"]) == 1
        assert "FACT-01" in result["warnings"][0]
        assert "past its valid_until" in result["warnings"][0]

    @pytest.mark.asyncio
    async def test_lint_warnings_no_shared_state(self, mock_supabase, auth_user, kit_id):
        """Test that multiple requests don't share warning state."""
        from app.api.kits import lint_kit
        from datetime import date, timedelta
        
        mock_supabase.get_kit.return_value = {
            "id": str(kit_id),
            "org_id": "org-123",
            "name": "My Kit",
            "status": "active",
            "version": 1,
        }
        mock_supabase.get_kit_rules.return_value = []
        
        # First request with expired fact
        past_date = (date.today() - timedelta(days=1)).isoformat()
        mock_supabase.get_kit_facts.return_value = [
            {
                "fact_key": "FACT-01",
                "statement": "Test fact",
                "source_note": "Test source",
                "valid_until": past_date,
            }
        ]
        
        result1 = await lint_kit(kit_id=kit_id, user=auth_user)
        
        # Second request without expired fact
        mock_supabase.get_kit_facts.return_value = [
            {
                "fact_key": "FACT-02",
                "statement": "Test fact 2",
                "source_note": "Test source",
                "valid_until": (date.today() + timedelta(days=30)).isoformat(),
            }
        ]
        
        result2 = await lint_kit(kit_id=kit_id, user=auth_user)
        
        # Each response should have its own warnings
        assert len(result1["warnings"]) == 1
        assert "FACT-01" in result1["warnings"][0]
        assert len(result2["warnings"]) == 0
        assert result2["warnings"] == []