"""Groq LLM provider implementation.

This module implements the Provider protocol for Groq using the official
`groq` Python SDK with `AsyncGroq` client.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from groq import AsyncGroq
from groq.types.chat import ChatCompletion

from app.models.pipeline import (
    ProviderError,
    ProviderRequest,
    ProviderResult,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BadOutputError,
    BlockedError,
)
from app.llm.token_budget import estimate_tokens, TokenBudgetExceededError

logger = logging.getLogger(__name__)


class GroqProvider:
    """Groq LLM provider using the official AsyncGroq client.

    Implements strict JSON Schema structured output via Groq's
    `response_format={"type": "json_schema", "json_schema": {...}}` parameter.

    Model: openai/gpt-oss-120b (supports strict mode constrained decoding)
    """

    # Groq free-tier limits (organization-specific, must be verified in console)
    DEFAULT_TPM_LIMIT = 8000
    DEFAULT_RPM_LIMIT = 30
    DEFAULT_RPD_LIMIT = 1000
    DEFAULT_TPD_LIMIT = 200_000

    # Safety margin for token budgeting (20%)
    TOKEN_SAFETY_MARGIN = 0.20

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        tpm_limit: Optional[int] = None,
        rpm_limit: Optional[int] = None,
    ):
        """Initialize the Groq provider.

        Args:
            api_key: Groq API key (must not be logged).
            model: Model identifier. Default: openai/gpt-oss-120b.
            tpm_limit: Tokens per minute limit for budgeting. Default: 8000.
            rpm_limit: Requests per minute limit. Default: 30.
        """
        if not api_key or not api_key.strip():
            raise ValueError("Groq API key must be provided and non-empty")

        self._api_key = api_key
        self._model = model
        self._tpm_limit = tpm_limit or self.DEFAULT_TPM_LIMIT
        self._rpm_limit = rpm_limit or self.DEFAULT_RPM_LIMIT
        self._client = AsyncGroq(api_key=api_key, timeout=45.0)

    @property
    def model(self) -> str:
        """Return the model identifier."""
        return self._model

    def _build_groq_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Transform the shared OUTPUT_SCHEMA into Groq strict-mode compatible schema.

        Groq strict mode requires:
        - All properties in the `required` array
        - `additionalProperties: false` on all objects
        - Nullable fields represented as `{"type": ["string", "null"]}`

        Args:
            schema: The shared OUTPUT_SCHEMA from prompt_builder.py

        Returns:
            Groq-compatible schema with strict mode adaptations.
        """
        import copy
        adapted = copy.deepcopy(schema)

        def adapt_object(obj: Dict[str, Any]) -> Dict[str, Any]:
            if obj.get("type") != "object":
                return obj

            properties = obj.get("properties", {})
            required = obj.get("required", [])

            # Ensure all properties are in required (Groq strict mode requirement)
            all_props = list(properties.keys())
            for prop in all_props:
                if prop not in required:
                    required.append(prop)

            # Set additionalProperties: false
            obj["additionalProperties"] = False
            obj["required"] = required

            # Recursively adapt nested objects
            for prop_name, prop_schema in properties.items():
                if isinstance(prop_schema, dict):
                    if prop_schema.get("type") == "object":
                        properties[prop_name] = adapt_object(prop_schema)
                    elif prop_schema.get("type") == "array" and "items" in prop_schema:
                        items = prop_schema["items"]
                        if isinstance(items, dict) and items.get("type") == "object":
                            properties[prop_name]["items"] = adapt_object(items)

            return obj

        return adapt_object(adapted)

    def _detect_refusal(self, content: str) -> bool:
        """Detect if the response contains a safety refusal.

        Args:
            content: The raw response content from the model.

        Returns:
            True if a refusal is detected, False otherwise.
        """
        if not content or not content.strip():
            return True

        content_stripped = content.strip()
        content_lower = content_stripped.lower()

        # First, check if content is valid JSON (handles whitespace, pretty-print, etc.)
        # If it parses as JSON, it's a structured response, not a natural language refusal.
        try:
            json.loads(content_stripped)
            # Valid JSON - not a refusal
            return False
        except json.JSONDecodeError:
            # Not valid JSON - could be a refusal or truncated output
            pass

        # Not valid JSON - check for natural language refusal patterns
        refusal_indicators = [
            "i cannot",
            "i can't",
            "i am unable",
            "i'm unable",
            "as an ai",
            "safety",
            "refuse",
            "blocked",
            "violation",
            "cannot comply",
            "not appropriate",
        ]

        # Check for explicit refusal patterns in natural language
        for indicator in refusal_indicators:
            if indicator in content_lower:
                return True

        return False

    def _detect_truncation(self, content: str, finish_reason: str) -> bool:
        """Detect if the response was truncated.

        Args:
            content: The raw response content.
            finish_reason: The finish reason from the provider.

        Returns:
            True if truncation is detected, False otherwise.
        """
        if finish_reason in ("length", "max_tokens", "token_limit"):
            return True

        # Check for incomplete JSON (common truncation indicator)
        content_stripped = content.strip()
        if content_stripped and not content_stripped.endswith("}"):
            return True

        # Check for unclosed brackets/braces
        open_braces = content_stripped.count("{")
        close_braces = content_stripped.count("}")
        open_brackets = content_stripped.count("[")
        close_brackets = content_stripped.count("]")

        return open_braces != close_braces or open_brackets != close_brackets

    def _parse_response(
        self,
        completion: ChatCompletion,
        request: ProviderRequest,
    ) -> ProviderResult:
        """Parse the Groq completion into a ProviderResult.

        Args:
            completion: The ChatCompletion from Groq.
            request: The original ProviderRequest.

        Returns:
            ProviderResult with parsed data.

        Raises:
            BadOutputError: If response is invalid, empty, or truncated.
            BlockedError: If safety refusal detected.
        """
        if not completion.choices:
            raise BadOutputError("Empty response: no choices returned")

        choice = completion.choices[0]
        content = choice.message.content or ""
        finish_reason = choice.finish_reason or "unknown"

        # Check for safety refusal FIRST (before JSON parsing)
        if self._detect_refusal(content):
            raise BlockedError("Provider returned safety refusal")

        # Validate JSON structure
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise BadOutputError(f"Invalid JSON in response: {e}")

        # Check for truncation (only after successful JSON parse)
        if self._detect_truncation(content, finish_reason):
            raise BadOutputError(
                f"Response appears truncated (finish_reason: {finish_reason})"
            )

        # Validate top-level structure
        if not isinstance(parsed, dict) or "findings" not in parsed:
            raise BadOutputError("Response missing 'findings' object")

        findings = parsed["findings"]
        if not isinstance(findings, list):
            raise BadOutputError("'findings' must be an array")

        # Validate each finding against ModelFindingCandidate
        from app.models.pipeline import ModelFindingCandidate
        for i, finding in enumerate(findings):
            try:
                ModelFindingCandidate.model_validate(finding)
            except Exception as e:
                raise BadOutputError(f"Finding {i} validation failed: {e}")

        # Extract token usage
        input_tokens = 0
        output_tokens = 0
        if completion.usage:
            input_tokens = completion.usage.prompt_tokens or 0
            output_tokens = completion.usage.completion_tokens or 0

        return ProviderResult(
            raw_json=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            latency_ms=0,  # Will be set by caller
            finish_reason=finish_reason,
        )

    async def generate_findings(self, request: ProviderRequest) -> ProviderResult:
        """Generate findings using Groq's structured output.

        Args:
            request: The provider request with system instruction, user content,
                     output schema, and generation parameters.

        Returns:
            ProviderResult containing the parsed response and metadata.

        Raises:
            ProviderError subclasses for various failure modes.
        """
        start_time = time.perf_counter()

        # Token budget check
        total_input_text = request.system_instruction + request.user_content
        estimated_input_tokens = estimate_tokens(total_input_text)
        estimated_total_tokens = estimated_input_tokens + request.output_limit

        # Apply safety margin
        safe_limit = int(self._tpm_limit * (1 - self.TOKEN_SAFETY_MARGIN))
        if estimated_total_tokens > safe_limit:
            raise TokenBudgetExceededError(
                f"Request exceeds safe token budget: "
                f"estimated {estimated_total_tokens} tokens > safe limit {safe_limit} "
                f"(TPM limit: {self._tpm_limit}, margin: {self.TOKEN_SAFETY_MARGIN * 100:.0f}%)"
            )

        # Build Groq-compatible schema
        groq_schema = self._build_groq_schema(request.output_schema)

        # Prepare messages
        messages = [
            {"role": "system", "content": request.system_instruction},
            {"role": "user", "content": request.user_content},
        ]

        # Prepare request parameters
        request_params = {
            "model": self._model,
            "messages": messages,
            "temperature": request.randomness,
            "max_tokens": request.output_limit,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "findings_schema",
                    "strict": True,
                    "schema": groq_schema,
                },
            },
        }

        # Single retry for transient failures
        max_retries = 1
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                # Respect timeout
                completion = await asyncio.wait_for(
                    self._client.chat.completions.create(**request_params),
                    timeout=request.timeout_seconds,
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)

                result = self._parse_response(completion, request)
                result.latency_ms = latency_ms

                logger.info(
                    "groq_request_completed",
                    extra={
                        "model": self._model,
                        "latency_ms": latency_ms,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "finish_reason": result.finish_reason,
                        "attempt": attempt + 1,
                    },
                )

                return result

            except asyncio.TimeoutError as e:
                last_exception = TimeoutError(
                    f"Request timed out after {request.timeout_seconds}s"
                )
                logger.warning(
                    "groq_timeout",
                    extra={"model": self._model, "attempt": attempt + 1},
                )

            except Exception as e:
                # Map Groq SDK exceptions to our error hierarchy
                # Re-raise BlockedError and BadOutputError immediately (non-retryable)
                if isinstance(e, (BlockedError, BadOutputError)):
                    raise

                error_msg = str(e)
                error_lower = error_msg.lower()

                if "rate limit" in error_lower or "429" in error_lower:
                    # Extract retry_after if available
                    retry_after = None
                    if hasattr(e, "response") and e.response is not None:
                        retry_after_header = e.response.headers.get("retry-after")
                        if retry_after_header:
                            try:
                                retry_after = int(retry_after_header)
                            except ValueError:
                                pass

                    last_exception = RateLimitedError(
                        "Groq rate limit exceeded",
                        retry_after=retry_after,
                    )
                    logger.warning(
                        "groq_rate_limited",
                        extra={"model": self._model, "retry_after": retry_after},
                    )

                elif "timeout" in error_lower:
                    last_exception = TimeoutError(f"Groq request timeout: {error_msg}")
                    logger.warning(
                        "groq_timeout_error",
                        extra={"model": self._model},
                    )

                elif any(
                    code in error_lower
                    for code in ["500", "502", "503", "504", "internal server error", "service unavailable"]
                ):
                    last_exception = UnavailableError(f"Groq service unavailable: {error_msg}")
                    logger.warning(
                        "groq_unavailable",
                        extra={"model": self._model, "error": error_msg},
                    )

                elif "authentication" in error_lower or "unauthorized" in error_lower or "401" in error_lower:
                    # Authentication failure - do not retry, not a transient error
                    raise ProviderError(f"Groq authentication failed: {error_msg}")

                elif "json_schema" in error_lower or "strict" in error_lower or "validation" in error_lower:
                    last_exception = BadOutputError(f"Groq schema validation failed: {error_msg}")
                    logger.warning(
                        "groq_schema_validation_failed",
                        extra={"model": self._model, "error": error_msg},
                    )

                else:
                    # Unknown error - treat as bad output
                    last_exception = BadOutputError(f"Groq error: {error_msg}")
                    logger.warning(
                        "groq_unknown_error",
                        extra={"model": self._model, "error": error_msg},
                    )

            # Wait before retry (only for retryable errors)
            if attempt < max_retries and last_exception is not None:
                wait_time = 0
                if isinstance(last_exception, RateLimitedError) and last_exception.retry_after:
                    wait_time = min(last_exception.retry_after, 10)
                elif isinstance(last_exception, (TimeoutError, UnavailableError)):
                    wait_time = min(2 ** attempt, 10)  # Exponential backoff capped at 10s

                if wait_time > 0:
                    logger.info(
                        "groq_retry_wait",
                        extra={"model": self._model, "wait_seconds": wait_time, "attempt": attempt + 1},
                    )
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise ProviderError("Groq request failed after retries")