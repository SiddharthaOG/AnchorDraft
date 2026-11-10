"""Tests for lint endpoint limits enforcement."""
import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4
from app.auth.dependencies import AuthUser


class TestKitLintLimits:
    """Tests for lint endpoint limit enforcement."""

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
        return AuthUser(
            user_id="user-123",
            org_id="org-123",
            roles=["owner"]
        )

    @pytest.fixture
    def kit_id(self):
        return UUID("11111111-1111-1111-1111-111111111111")

    def _setup_valid_kit(self, mock_supabase, kit_id, rules, facts):
        """Helper to set up a valid kit with given rules and facts."""
        mock_supabase.get_kit.return_value = {
            "id": str(kit_id),
            "org_id": "org-123",
            "name": "My Kit",
            "status": "active",
            "version": 1,
        }
        mock_supabase.get_kit_rules.return_value = rules
        mock_supabase.get_kit_facts.return_value = facts

    @pytest.mark.asyncio
    async def test_lint_deterministic_rules_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 50 deterministic rules is allowed."""
        from app.api.kits import lint_kit
        
        rules = []
        for i in range(50):
            rules.append({
                "rule_key": f"RULE-{i:02d}",
                "category": "terminology",
                "severity": "medium",
                "title": f"Rule {i}",
                "guideline_text": f"Guideline {i}",
                "check_kind": "deterministic",
                "config": {"check": "phrase_list", "phrases": ["test"]},
                "needs_reviewer": False,
            })
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        # Should not have TOO_MANY_DETERMINISTIC_RULES error
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_DETERMINISTIC_RULES" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_deterministic_rules_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 51 deterministic rules produces TOO_MANY_DETERMINISTIC_RULES error."""
        from app.api.kits import lint_kit
        
        rules = []
        for i in range(51):
            rules.append({
                "rule_key": f"RULE-{i:02d}",
                "category": "terminology",
                "severity": "medium",
                "title": f"Rule {i}",
                "guideline_text": f"Guideline {i}",
                "check_kind": "deterministic",
                "config": {"check": "phrase_list", "phrases": ["test"]},
                "needs_reviewer": False,
            })
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_DETERMINISTIC_RULES" in error_codes
        issue = next(i for i in result["issues"] if i["code"] == "TOO_MANY_DETERMINISTIC_RULES")
        assert issue["message"] == "Kit exceeds maximum of 50 deterministic rules (has 51)"

    @pytest.mark.asyncio
    async def test_lint_term_map_entries_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 term_map entries is allowed."""
        from app.api.kits import lint_kit
        
        entries = [{"avoid": [f"term{i}"], "prefer": f"prefer{i}"} for i in range(100)]
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Term Map Rule",
            "guideline_text": "Use preferred terms",
            "check_kind": "deterministic",
            "config": {"check": "term_map", "entries": entries},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_TERM_MAP_ENTRIES" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_term_map_entries_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 term_map entries produces TOO_MANY_TERM_MAP_ENTRIES error."""
        from app.api.kits import lint_kit
        
        entries = [{"avoid": [f"term{i}"], "prefer": f"prefer{i}"} for i in range(101)]
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Term Map Rule",
            "guideline_text": "Use preferred terms",
            "check_kind": "deterministic",
            "config": {"check": "term_map", "entries": entries},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_TERM_MAP_ENTRIES" in error_codes

    @pytest.mark.asyncio
    async def test_lint_avoid_terms_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 avoid terms per entry is allowed."""
        from app.api.kits import lint_kit
        
        entries = [{
            "avoid": [f"term{i}" for i in range(100)],
            "prefer": "prefer",
        }]
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Term Map Rule",
            "guideline_text": "Use preferred terms",
            "check_kind": "deterministic",
            "config": {"check": "term_map", "entries": entries},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_AVOID_TERMS" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_avoid_terms_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 avoid terms produces TOO_MANY_AVOID_TERMS error."""
        from app.api.kits import lint_kit
        
        entries = [{
            "avoid": [f"term{i}" for i in range(101)],
            "prefer": "prefer",
        }]
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Term Map Rule",
            "guideline_text": "Use preferred terms",
            "check_kind": "deterministic",
            "config": {"check": "term_map", "entries": entries},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_AVOID_TERMS" in error_codes

    @pytest.mark.asyncio
    async def test_lint_term_length_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 character term is allowed."""
        from app.api.kits import lint_kit
        
        entries = [{
            "avoid": ["a" * 100],
            "prefer": "b",
        }]
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Term Map Rule",
            "guideline_text": "Use preferred terms",
            "check_kind": "deterministic",
            "config": {"check": "term_map", "entries": entries},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TERM_TOO_LONG" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_term_length_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 character term produces TERM_TOO_LONG error."""
        from app.api.kits import lint_kit
        
        entries = [{
            "avoid": ["a" * 101],
            "prefer": "b",
        }]
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Term Map Rule",
            "guideline_text": "Use preferred terms",
            "check_kind": "deterministic",
            "config": {"check": "term_map", "entries": entries},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TERM_TOO_LONG" in error_codes

    @pytest.mark.asyncio
    async def test_lint_phrases_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 phrases is allowed."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Phrase List Rule",
            "guideline_text": "Avoid these phrases",
            "check_kind": "deterministic",
            "config": {"check": "phrase_list", "phrases": [f"phrase{i}" for i in range(100)]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_PHRASES" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_phrases_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 phrases produces TOO_MANY_PHRASES error."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Phrase List Rule",
            "guideline_text": "Avoid these phrases",
            "check_kind": "deterministic",
            "config": {"check": "phrase_list", "phrases": [f"phrase{i}" for i in range(101)]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_PHRASES" in error_codes

    @pytest.mark.asyncio
    async def test_lint_phrase_length_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 character phrase is allowed."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Phrase List Rule",
            "guideline_text": "Avoid these phrases",
            "check_kind": "deterministic",
            "config": {"check": "phrase_list", "phrases": ["a" * 100]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "PHRASE_TOO_LONG" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_phrase_length_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 character phrase produces PHRASE_TOO_LONG error."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "terminology",
            "severity": "medium",
            "title": "Phrase List Rule",
            "guideline_text": "Avoid these phrases",
            "check_kind": "deterministic",
            "config": {"check": "phrase_list", "phrases": ["a" * 101]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "PHRASE_TOO_LONG" in error_codes

    @pytest.mark.asyncio
    async def test_lint_generic_terms_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 generic terms is allowed."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "images",
            "severity": "medium",
            "title": "Missing Alt Text Rule",
            "guideline_text": "All images must have alt text",
            "check_kind": "deterministic",
            "config": {"check": "missing_alt_text", "min_length": 5, "generic": [f"img{i}" for i in range(100)]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_GENERIC_TERMS" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_generic_terms_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 generic terms produces TOO_MANY_GENERIC_TERMS error."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "images",
            "severity": "medium",
            "title": "Missing Alt Text Rule",
            "guideline_text": "All images must have alt text",
            "check_kind": "deterministic",
            "config": {"check": "missing_alt_text", "min_length": 5, "generic": [f"img{i}" for i in range(101)]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_GENERIC_TERMS" in error_codes

    @pytest.mark.asyncio
    async def test_lint_when_any_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 when_any terms is allowed."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "legal",
            "severity": "high",
            "title": "Required Disclosure Rule",
            "guideline_text": "Disclose when required",
            "check_kind": "deterministic",
            "config": {"check": "required_disclosure", "when_any": [f"trigger{i}" for i in range(100)], "require_any": ["disclosure"]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_WHEN_ANY_TERMS" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_when_any_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 when_any terms produces TOO_MANY_WHEN_ANY_TERMS error."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "legal",
            "severity": "high",
            "title": "Required Disclosure Rule",
            "guideline_text": "Disclose when required",
            "check_kind": "deterministic",
            "config": {"check": "required_disclosure", "when_any": [f"trigger{i}" for i in range(101)], "require_any": ["disclosure"]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_WHEN_ANY_TERMS" in error_codes

    @pytest.mark.asyncio
    async def test_lint_require_any_at_limit(self, mock_supabase, auth_user, kit_id):
        """Test exactly 100 require_any terms is allowed."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "legal",
            "severity": "high",
            "title": "Required Disclosure Rule",
            "guideline_text": "Disclose when required",
            "check_kind": "deterministic",
            "config": {"check": "required_disclosure", "when_any": ["trigger"], "require_any": [f"disclosure{i}" for i in range(100)]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_REQUIRE_ANY_TERMS" not in error_codes

    @pytest.mark.asyncio
    async def test_lint_require_any_over_limit(self, mock_supabase, auth_user, kit_id):
        """Test 101 require_any terms produces TOO_MANY_REQUIRE_ANY_TERMS error."""
        from app.api.kits import lint_kit
        
        rules = [{
            "rule_key": "RULE-01",
            "category": "legal",
            "severity": "high",
            "title": "Required Disclosure Rule",
            "guideline_text": "Disclose when required",
            "check_kind": "deterministic",
            "config": {"check": "required_disclosure", "when_any": ["trigger"], "require_any": [f"disclosure{i}" for i in range(101)]},
            "needs_reviewer": False,
        }]
        
        self._setup_valid_kit(mock_supabase, kit_id, rules, [])
        
        result = await lint_kit(kit_id=kit_id, user=auth_user)
        
        error_codes = [i["code"] for i in result["issues"] if i["severity"] == "error"]
        assert "TOO_MANY_REQUIRE_ANY_TERMS" in error_codes