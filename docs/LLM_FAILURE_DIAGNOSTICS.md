# LLM Failure Diagnostics and Staging Runbook

## Purpose

Make every review-provider failure diagnosable without exposing draft text, system prompts, API keys, or other secrets in Render logs.

## 1. Startup configuration evidence

On provider construction, Render logs one of:

- `provider_pair_configured` / `vision_provider_pair_configured`
- `provider_fallback_not_configured`

These events include provider/model identifiers, the configured fallback-enabled boolean, and whether a fallback adapter was actually constructed. They never include credentials.

Interpretation:

- `fallback_enabled=false` with `reason=disabled_by_configuration`: environment configuration disabled fallback.
- `reason=same_provider_model`: primary and fallback resolve to the same model, so no useful fallback exists.
- `fallback_available=true`: the adapter was constructed; this does not prove the provider API is reachable.
- Missing startup events: inspect service startup logs and verify the deployment is running the expected commit.

## 2. Request-level event sequence

For one review, correlate events by timestamp and the existing request/kit identifiers emitted by the review pipeline. The provider layer emits:

1. `provider_primary_attempt`
2. `gemini_request_started` (Gemini adapter) or the Groq request events
3. One of `gemini_request_completed`, `gemini_timeout`, `gemini_unavailable`, `gemini_rate_limited`, `groq_request_started`, `groq_request_completed`, `groq_timeout`, `groq_unavailable`, `groq_rate_limited`, `groq_vision_request_started`, `groq_vision_request_completed`, `groq_vision_timeout`, `groq_vision_request_failed`, or a safe mapped failure
4. One of `provider_primary_success`, `provider_primary_timeout`, or `provider_primary_failed`
5. If eligible and configured: `provider_fallback_attempt`
6. One of `provider_fallback_success` or `provider_both_failed`

Timing fields include allocated timeout, attempt duration, remaining fallback budget, and total elapsed time. Error fields are categories/types only. Do not add prompt, draft, redacted content, or API-key values to these logs.

## 3. Cross-provider configuration

For Gemini-primary / Groq-fallback staging:

- `LLM_PROVIDER=gemini`
- `LLM_FALLBACK_ENABLED=true`
- `LLM_FALLBACK_PROVIDER=groq`
- `GROQ_MODEL=openai/gpt-oss-120b` for text findings
- `GROQ_VISION_MODEL=qwen/qwen3.8-27b` for visual findings
- `GROQ_TPM_LIMIT=8000` as a conservative free-tier default; raise it only after checking the organization's exact limit in Groq Console

Text and vision use separate Groq model settings. Do not point visual requests at the text-only GPT-OSS model. The selected Qwen model supports multimodal input and strict structured outputs on Groq. The 8K TPM default is deliberately conservative: Groq publishes different limits by plan and model, so never assume the Developer-plan limit applies to a Free organization.

## 4. Timeout policy

The wrapper owns the overall review deadline and reserves time for the fallback adapter. Gemini adapter retries share one provider deadline and skip retries when the remaining budget cannot cover the backoff and a meaningful second attempt. The outer wrapper remains the final deadline guard for both providers.

## 5. Google AI Studio cross-check

Google AI Studio's **Logs and Datasets** view can provide a provider-side record of supported Gemini API requests and responses when project logging is enabled. Use it to compare the model, timestamp, status, and provider-side latency with Render's request events.

Important privacy boundary: provider-side logging may expose request/response content. Do not enable it for production AnchorDraft traffic until the team has explicitly reviewed the data-retention and confidentiality implications. If using it for diagnosis, prefer a separate test project/key and a minimal synthetic prompt. Never paste a real brand draft or confidential content into an ad-hoc probe.

AI Studio logs are supplementary evidence. A request that fails before reaching Google's API, or a failure not covered by its logging configuration, may not have a corresponding record. Render's sanitized application events remain the primary end-to-end trace.

## 6. Staging verification checklist

- [ ] Confirm Render staging is live on the intended commit.
- [ ] Confirm startup event reports the expected primary model, fallback-enabled state, fallback model, and `fallback_available=true`.
- [ ] Submit one synthetic review through the staging UI.
- [ ] Confirm the primary attempt event and either primary success or a classified primary failure.
- [ ] If primary fails transiently, confirm a fallback-attempt event includes a positive fallback budget.
- [ ] Confirm fallback success returns model findings; a successful deterministic-only review is not counted as LLM success.
- [ ] If both providers fail, confirm both safe error categories and durations are visible.
- [ ] Confirm production branch/deployment remains unchanged.

## 7. What this does not prove

Unit tests validate the deadline and fallback control flow with mocked providers. They do not prove the configured Gemini models are available, quota is sufficient, the API key is valid, or that a live request will succeed. Only a real staging review can prove the integration path for the deployed configuration.
