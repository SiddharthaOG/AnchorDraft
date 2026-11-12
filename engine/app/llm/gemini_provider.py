"""Gemini LLM provider implementation.

This module implements the Provider protocol for Google Gemini API using
the official `google-genai` Python SDK with native async support.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

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


class GeminiProvider:
    """Gemini LLM provider using the official google-genai SDK.

    Implements structured JSON output via Gemini's OpenAPI-compatible `response_schema`.

    Model: gemini-3.8-flash (current stable Flash model with structured output)
    """

    # Default conservative limits (account/project-dependent, must be verified in AI Studio)
    DEFAULT_TPM_LIMIT = 250_000
    DEFAULT_RPM_LIMIT = 15
    DEFAULT_RPD_LIMIT = 500

    # Safety margin for token budgeting (20%)
    TOKEN_SAFETY_MARGIN = 0.20

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.8-flash",
        tpm_limit: Optional[int] = None,
        rpm_limit: Optional[int] = None,
    ):
        """Initialize the Gemini provider.

        Args:
            api_key: Google AI Studio / Gemini API key (must not be logged).
            model: Model identifier. Default: gemini-3.8-flash.
            tpm_limit: Tokens per minute limit for budgeting. Default: 250000.
            rpm_limit: Requests per minute limit. Default: 15.
        """
        if not api_key or not api_key.strip():
            raise ValueError("Gemini API key must be provided and non-empty")

        self._api_key = api_key
        self._model = model
        self._tpm_limit = tpm_limit or self.DEFAULT_TPM_LIMIT
        self._rpm_limit = rpm_limit or self.DEFAULT_RPM_LIMIT
        self._client = genai.Client(api_key=api_key)

    @property
    def model(self) -> str:
        """Return the model identifier."""
        return self._model

    def _build_gemini_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Transform the shared OUTPUT_SCHEMA into Gemini-compatible schema.

        Gemini's structured output uses a subset of JSON Schema (OpenAPI-like).
        It supports: enum, nullable, required, minLength, type arrays.

        Args:
            schema: The shared OUTPUT_SCHEMA from prompt_builder.py

        Returns:
            Gemini-compatible schema.
        """
        import copy
        adapted = copy.deepcopy(schema)

        # Gemini uses the schema directly with response_schema
        # Ensure it's in a compatible format
        def adapt_for_gemini(obj: Dict[str, Any]) -> Dict[str, Any]:
            if not isinstance(obj, dict):
                return obj

            # The installed google-genai 0.3.x SDK models response_schema using
            # OpenAPI Schema, where nullable is a boolean rather than a JSON
            # Schema type union. Convert only the supported T|null form.
            if "type" in obj and isinstance(obj["type"], list):
                types_in_union = obj["type"]
                non_null_types = [value for value in types_in_union if value != "null"]
                if len(non_null_types) == 1 and len(types_in_union) == 2:
                    obj["type"] = non_null_types[0]
                    obj["nullable"] = True
                else:
                    raise ValueError("Gemini response_schema supports only single-type nullable unions")

            # Recursively adapt nested objects
            if "properties" in obj:
                for prop_name, prop_schema in obj["properties"].items():
                    obj["properties"][prop_name] = adapt_for_gemini(prop_schema)

            if "items" in obj and isinstance(obj["items"], dict):
                obj["items"] = adapt_for_gemini(obj["items"])

            return obj

        return adapt_for_gemini(adapted)

    def _detect_refusal(self, content: str, response: Any) -> bool:
        """Detect if the response contains a safety refusal.

        Args:
            content: The raw response text.
            response: The full response object from Gemini.

        Returns:
            True if a safety refusal is detected, False otherwise.
        """
        if not content or not content.strip():
            return True

        content_stripped = content.strip()
        content_lower = content_stripped.lower()

        # Check response metadata for safety ratings FIRST (before JSON check)
        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "finish_reason"):
                    if candidate.finish_reason in (
                        "SAFETY",
                        "RECITATION",
                        "BLOCKED",
                    ):
                        return True
                if hasattr(candidate, "safety_ratings"):
                    for rating in candidate.safety_ratings:
                        if hasattr(rating, "probability") and rating.probability in (
                            "HIGH",
                            "MEDIUM",
                        ):
                            return True

        # Check if content is valid JSON (handles whitespace, pretty-print, etc.)
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
        if finish_reason in ("MAX_TOKENS", "TOKEN_LIMIT", "LENGTH"):
            return True

        # Check for incomplete JSON
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
        response: Any,
        request: ProviderRequest,
    ) -> ProviderResult:
        """Parse the Gemini response into a ProviderResult.

        Args:
            response: The response from Gemini's generate_content_async.
            request: The original ProviderRequest.

        Returns:
            ProviderResult with parsed data.

        Raises:
            BadOutputError: If response is invalid, empty, or truncated.
            BlockedError: If safety refusal detected.
        """
        if not response.candidates or len(response.candidates) == 0:
            raise BadOutputError("Empty response: no candidates returned")

        candidate = response.candidates[0]

        # Get content
        content = ""
        if hasattr(candidate, "content") and candidate.content:
            if hasattr(candidate.content, "parts") and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        content += part.text

        if not content:
            # Check if blocked
            finish_reason = getattr(candidate, "finish_reason", "UNKNOWN")
            if finish_reason in ("SAFETY", "RECITATION", "BLOCKED"):
                raise BlockedError("Provider returned safety refusal")
            raise BadOutputError("Empty response content")

        finish_reason = getattr(candidate, "finish_reason", "UNKNOWN")

        # Check for safety refusal FIRST (before JSON parsing)
        if self._detect_refusal(content, response):
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
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return ProviderResult(
            raw_json=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            latency_ms=0,  # Will be set by caller
            finish_reason=finish_reason,
        )

    async def generate_findings(self, request: ProviderRequest) -> ProviderResult:
        """Generate findings using Gemini's structured output.

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

        # Adapt the shared JSON Schema to the OpenAPI Schema subset exposed by
        # the pinned google-genai SDK. In particular, translate T|null unions
        # to the SDK's nullable flag before constructing GenerateContentConfig.
        gemini_schema = self._build_gemini_schema(request.output_schema)
        generation_config = types.GenerateContentConfig(
            temperature=request.randomness,
            max_output_tokens=request.output_limit,
            response_mime_type="application/json",
            response_schema=gemini_schema,
        )

        # Combine system instruction and user content for Gemini
        # Gemini uses a single content field with system instruction as prefix
        full_content = f"{request.system_instruction}\n\n{request.user_content}"

        # Single retry for transient failures
        max_retries = 1
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                # Respect timeout
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model,
                        contents=full_content,
                        config=generation_config,
                    ),
                    timeout=request.timeout_seconds,
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)

                result = self._parse_response(response, request)
                result.latency_ms = latency_ms

                logger.info(
                    "gemini_request_completed",
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

            except asyncio.TimeoutError:
                last_exception = TimeoutError(
                    f"Request timed out after {request.timeout_seconds}s"
                )
                logger.warning(
                    "gemini_timeout",
                    extra={"model": self._model, "attempt": attempt + 1},
                )

            except Exception as e:
                # Map Gemini SDK exceptions to our error hierarchy
                error_msg = str(e)
                error_lower = error_msg.lower()

                if "rate limit" in error_lower or "429" in error_lower or "quota" in error_lower:
                    retry_after = None
                    if hasattr(e, "retry_delay") and e.retry_delay:
                        try:
                            retry_after = int(e.retry_delay)
                        except (ValueError, TypeError):
                            pass

                    last_exception = RateLimitedError(
                        "Gemini rate limit exceeded",
                        retry_after=retry_after,
                    )
                    logger.warning(
                        "gemini_rate_limited",
                        extra={"model": self._model, "retry_after": retry_after},
                    )

                elif "timeout" in error_lower:
                    last_exception = TimeoutError(f"Gemini request timeout: {error_msg}")
                    logger.warning(
                        "gemini_timeout_error",
                        extra={"model": self._model},
                    )

                elif any(
                    code in error_lower
                    for code in ["500", "502", "503", "504", "internal", "unavailable"]
                ):
                    last_exception = UnavailableError(f"Gemini service unavailable: {error_msg}")
                    logger.warning(
                        "gemini_unavailable",
                        extra={"model": self._model, "error": error_msg},
                    )

                elif "permission" in error_lower and "safety" in error_lower:
                    # Safety-related permission denied - treat as blocked
                    last_exception = BlockedError("Gemini safety filter triggered")
                    logger.warning(
                        "gemini_safety_block",
                        extra={"model": self._model},
                    )

                elif "authentication" in error_lower or "unauthorized" in error_lower or "401" in error_lower or "api key" in error_lower:
                    # Authentication failure - do not retry
                    raise ProviderError(f"Gemini authentication failed: {error_msg}")

                elif "schema" in error_lower or "validation" in error_lower or "json" in error_lower:
                    last_exception = BadOutputError(f"Gemini schema validation failed: {error_msg}")
                    logger.warning(
                        "gemini_schema_validation_failed",
                        extra={
                            "model": self._model,
                            "error_type": type(e).__name__,
                            # Provider errors describe request/schema validation,
                            # not the user prompt or response payload. Keep bounded.
                            "error_detail": error_msg[:400],
                        },
                    )

                else:
                    # Unknown error
                    last_exception = BadOutputError(f"Gemini error: {error_msg}")
                    logger.warning(
                        "gemini_unknown_error",
                        extra={"model": self._model, "error": error_msg},
                    )

            # Wait before retry
            if attempt < max_retries and last_exception is not None:
                wait_time = 0
                if isinstance(last_exception, RateLimitedError) and last_exception.retry_after:
                    wait_time = min(last_exception.retry_after, 10)
                elif isinstance(last_exception, (TimeoutError, UnavailableError)):
                    wait_time = min(2 ** attempt, 10)

                if wait_time > 0:
                    logger.info(
                        "gemini_retry_wait",
                        extra={"model": self._model, "wait_seconds": wait_time, "attempt": attempt + 1},
                    )
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise ProviderError("Gemini request failed after retries")