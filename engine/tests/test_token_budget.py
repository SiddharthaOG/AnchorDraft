"""Tests for the token budget module."""

import pytest

from app.llm.token_budget import (
    estimate_tokens,
    estimate_request_tokens,
    check_token_budget,
    TokenBudgetExceededError,
    TokenEstimate,
    CHARS_PER_TOKEN,
)


class TestEstimateTokens:
    """Tests for the estimate_tokens function."""

    def test_empty_string(self):
        """Test empty string returns 0."""
        assert estimate_tokens("") == 0

    def test_none_returns_zero(self):
        """Test None returns 0."""
        assert estimate_tokens(None) == 0

    def test_short_string(self):
        """Test short string estimation."""
        # "test" = 4 chars, at 4 chars/token = 1 token + 1 = 2
        assert estimate_tokens("test") == 2

    def test_longer_string(self):
        """Test longer string estimation."""
        # 100 chars at 4 chars/token = 25 + 1 = 26
        text = "x" * 100
        assert estimate_tokens(text) == 26

    def test_conservative_estimation(self):
        """Test that estimation is conservative (rounds up)."""
        # 4 chars should be 1 token but we add 1
        assert estimate_tokens("abcd") == 2
        # 8 chars should be 2 tokens + 1 = 3
        assert estimate_tokens("abcdefgh") == 3


class TestEstimateRequestTokens:
    """Tests for estimate_request_tokens function."""

    def test_basic_estimation(self):
        """Test basic request token estimation."""
        system = "You are a reviewer."
        user = "Draft text here."
        output_limit = 4096

        estimate = estimate_request_tokens(system, user, output_limit)

        assert estimate.estimated_input_tokens > 0
        assert estimate.estimated_output_tokens == output_limit
        assert estimate.estimated_total_tokens == estimate.estimated_input_tokens + output_limit
        assert estimate.safe_limit == 0
        assert estimate.within_budget is False

    def test_large_input_estimation(self):
        """Test estimation with large input."""
        system = "x" * 10000
        user = "y" * 10000
        output_limit = 4096

        estimate = estimate_request_tokens(system, user, output_limit)

        # ~20000 chars / 4 = 5000 input tokens + 4096 output
        assert estimate.estimated_input_tokens > 5000
        assert estimate.estimated_total_tokens > 9000


class TestCheckTokenBudget:
    """Tests for check_token_budget function."""

    def test_passes_for_small_request(self):
        """Test that small requests pass budget check."""
        system = "Short instruction"
        user = "Short content"
        output_limit = 100
        tpm_limit = 8000

        estimate = check_token_budget(system, user, output_limit, tpm_limit, 0.20)

        assert estimate.within_budget is True
        assert estimate.safe_limit == 6400  # 8000 * 0.8

    def test_fails_for_large_request(self):
        """Test that large requests fail budget check."""
        system = "x" * 20000
        user = "y" * 20000
        output_limit = 4096
        tpm_limit = 8000

        with pytest.raises(TokenBudgetExceededError) as exc_info:
            check_token_budget(system, user, output_limit, tpm_limit, 0.20)

        assert "exceeds safe token budget" in str(exc_info.value)

    def test_custom_safety_margin(self):
        """Test custom safety margin."""
        system = "x" * 10000
        user = "y" * 10000
        output_limit = 4096
        tpm_limit = 10000

        # 10% margin = 9000 safe limit
        # Input ~5000 + output 4096 = ~9096 > 9000, should fail
        with pytest.raises(TokenBudgetExceededError):
            check_token_budget(system, user, output_limit, tpm_limit, 0.10)

        # 30% margin = 7000 safe limit, should also fail
        with pytest.raises(TokenBudgetExceededError):
            check_token_budget(system, user, output_limit, tpm_limit, 0.30)

    def test_zero_margin(self):
        """Test zero safety margin."""
        system = "Short"
        user = "Content"
        output_limit = 100
        tpm_limit = 1000

        estimate = check_token_budget(system, user, output_limit, tpm_limit, 0.0)

        assert estimate.safe_limit == 1000
        assert estimate.within_budget is True

    def test_error_message_contains_details(self):
        """Test that error message contains useful details."""
        system = "x" * 20000
        user = "y" * 20000
        output_limit = 4096
        tpm_limit = 8000

        with pytest.raises(TokenBudgetExceededError) as exc_info:
            check_token_budget(system, user, output_limit, tpm_limit, 0.20)

        error_msg = str(exc_info.value)
        assert "estimated" in error_msg
        assert "safe limit" in error_msg
        assert "TPM limit" in error_msg
        assert "margin" in error_msg


class TestTokenEstimateDataclass:
    """Tests for TokenEstimate dataclass."""

    def test_creation(self):
        """Test TokenEstimate creation."""
        estimate = TokenEstimate(
            estimated_input_tokens=100,
            estimated_output_tokens=50,
            estimated_total_tokens=150,
            safe_limit=6400,
            within_budget=True,
        )

        assert estimate.estimated_input_tokens == 100
        assert estimate.estimated_output_tokens == 50
        assert estimate.estimated_total_tokens == 150
        assert estimate.safe_limit == 6400
        assert estimate.within_budget is True


class TestTokenBudgetExceededError:
    """Tests for TokenBudgetExceededError."""

    def test_exception_message(self):
        """Test exception can be created with message."""
        error = TokenBudgetExceededError("Test message")
        assert str(error) == "Test message"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])