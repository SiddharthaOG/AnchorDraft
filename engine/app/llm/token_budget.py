"""Token budget estimation and validation.

This module provides conservative token estimation for request budgeting
to avoid exceeding provider free-tier TPM limits.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Conservative token estimation: ~4 characters per token for English text
# This is intentionally conservative to avoid underestimation
CHARS_PER_TOKEN = 4.0


class TokenBudgetExceededError(Exception):
    """Raised when a request exceeds the safe token budget."""
    pass


@dataclass
class TokenEstimate:
    """Result of token estimation."""
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    safe_limit: int
    within_budget: bool


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string.

    Uses a conservative character-based estimation (~4 chars/token for English).
    This is intentionally conservative to avoid exceeding limits.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count (rounded up).
    """
    if not text:
        return 0

    # Conservative: 4 characters per token
    estimated = len(text) / CHARS_PER_TOKEN
    return int(estimated) + 1  # Round up


def estimate_request_tokens(
    system_instruction: str,
    user_content: str,
    output_limit: int,
) -> TokenEstimate:
    """Estimate tokens for a complete provider request.

    Args:
        system_instruction: The system instruction text.
        user_content: The user content text.
        output_limit: The maximum output tokens configured.

    Returns:
        TokenEstimate with detailed breakdown.
    """
    input_text = system_instruction + user_content
    estimated_input = estimate_tokens(input_text)
    estimated_output = output_limit  # Conservative: assume full output budget used
    estimated_total = estimated_input + estimated_output

    return TokenEstimate(
        estimated_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        estimated_total_tokens=estimated_total,
        safe_limit=0,  # Will be set by caller
        within_budget=False,
    )


def check_token_budget(
    system_instruction: str,
    user_content: str,
    output_limit: int,
    tpm_limit: int,
    safety_margin: float = 0.20,
) -> TokenEstimate:
    """Check if a request fits within the token budget.

    Args:
        system_instruction: The system instruction text.
        user_content: The user content text.
        output_limit: The maximum output tokens configured.
        tpm_limit: The provider's tokens-per-minute limit.
        safety_margin: Safety margin as a fraction (default 20%).

    Returns:
        TokenEstimate with budget check result.

    Raises:
        TokenBudgetExceededError: If the request exceeds the safe budget.
    """
    estimate = estimate_request_tokens(system_instruction, user_content, output_limit)
    safe_limit = int(tpm_limit * (1 - safety_margin))
    estimate.safe_limit = safe_limit
    estimate.within_budget = estimate.estimated_total_tokens <= safe_limit

    if not estimate.within_budget:
        logger.warning(
            "token_budget_exceeded",
            extra={
                "estimated_input_tokens": estimate.estimated_input_tokens,
                "estimated_output_tokens": estimate.estimated_output_tokens,
                "estimated_total_tokens": estimate.estimated_total_tokens,
                "safe_limit": safe_limit,
                "tpm_limit": tpm_limit,
                "safety_margin": safety_margin,
            },
        )
        raise TokenBudgetExceededError(
            f"Request exceeds safe token budget: "
            f"estimated {estimate.estimated_total_tokens} tokens > safe limit {safe_limit} "
            f"(TPM limit: {tpm_limit}, margin: {safety_margin * 100:.0f}%)"
        )

    return estimate