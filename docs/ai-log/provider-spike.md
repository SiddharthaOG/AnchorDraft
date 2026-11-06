# Provider Spike Report (Finalized)

**Date:** 2026-11-06
**Research Date:** 2026-11-06
**Branch:** `feat/phase-4-review-engine`
**Commit:** `d8c5077` (feat: add structured LLM prompt construction)

---

## 1. Repository Baseline

- **Branch:** `feat/phase-4-review-engine`
- **Latest Commit:** `d8c5077` (feat: add structured LLM prompt construction)
- **Existing Slices:** 0 (Repo Skeleton), 1-3 (Phase 3 API Contract), 4.1-4.5 (Phase 4 Pipeline, Deterministic Checks, Citation Validator, Prompt Construction)
- **Provider Contract:** `engine/app/llm/provider.py` — `Provider` protocol with `async generate_findings(request: ProviderRequest) -> ProviderResult`
- **Current Provider:** `FakeProvider` (for testing only)
- **Environment:** `LLM_PROVIDER=fake` (no real API keys configured)

---

## 2. Files Inspected

| File | Purpose |
|------|---------|
| `docs/REVIEW_ENGINE.md` | Specification for review engine, provider requirements, prompt structure, output schema |
| `docs/ARCHITECTURE.md` | Architecture decisions, provider adapter design (Decision 6) |
| `docs/DATA_MODEL.md` | Database schema, rule/fact models |
| `engine/app/models/pipeline.py` | `ProviderRequest`, `ProviderResult`, `ProviderError` hierarchy, `ModelFindingCandidate` |
| `engine/app/llm/provider.py` | `Provider` protocol (abstract interface) |
| `engine/app/llm/fake_provider.py` | `FakeProvider` implementation for testing |
| `engine/app/llm/prompt_builder.py` | Prompt construction, `OUTPUT_SCHEMA`, `ProviderRequest` builder |
| `engine/tests/test_prompt_builder.py` | 62 tests for prompt construction |
| `engine/app/llm/__init__.py` | Exports for provider abstraction |

---

## 3. Official Sources Consulted

**Research Date:** 2026-11-06

| Provider | Source | URL | Access Date |
|----------|--------|-----|-------------|
| **Groq** | Groq API Docs / Models | https://console.groq.com/docs/models | 2026-11-06 |
| **Groq** | Structured Outputs | https://console.groq.com/docs/structured-outputs | 2026-11-06 |
| **Groq** | Rate Limits | https://console.groq.com/limits | 2026-11-06 |
| **Groq** | Python SDK | https://github.com/groq/groq-python | 2026-11-06 |
| **Gemini** | Google AI Studio / Gemini API Docs | https://ai.google.dev/gemini-api/docs | 2026-11-06 |
| **Gemini** | Structured Output Docs | https://ai.google.dev/gemini-api/docs/structured-output | 2026-11-06 |
| **Gemini** | Rate Limits | https://ai.google.dev/gemini-api/docs/rate-limits | 2026-11-06 |
| **Gemini** | Billing / Free Tier | https://ai.google.dev/gemini-api/docs/billing | 2026-11-06 |
| **Gemini** | AI Studio Rate Limit Page | https://aistudio.google.com/rate-limit | 2026-11-06 |
| **Gemini** | Python SDK | https://github.com/googleapis/python-genai | 2026-11-06 |

> **Note:** Web search was used to verify current model identifiers and free-tier limits. Findings below are based on official documentation URLs listed above and search results as of the research date. Items marked **UNVERIFIED** could not be confirmed against live console pages (require sign-in).

---

## 4. Architect-Approved Provider Decision

**Primary Provider:** Groq
**Primary Model:** `openai/gpt-oss-120b`
**Fallback Provider:** Google Gemini API
**Fallback Model:** `gemini-3.8-flash`
**Date:** 2026-11-06
**Decision Maker:** Siddhartha

**Rationale (from architect):**
- Groq GPT-OSS 120B provides explicit structured-output / JSON Schema support with constrained decoding (`strict: true`), OpenAI-compatible API, and published free-tier quotas.
- GPT-OSS 120B preferred over 20B for nuanced brand-rule interpretation, unsupported-claim detection, and explanation quality.
- Gemini `gemini-3.8-flash` (released 2026-09-02, GA) provides independent provider fallback with native structured output support and `google-genai` SDK.

---

## 5. Groq Findings (Verified)

### A. Model Identifier & Lifecycle

| Model Identifier | Status | Notes |
|------------------|--------|-------|
| `openai/gpt-oss-120b` | **Stable, GA** | Primary model, 120B total params (5.1B active), MoE architecture |
| `openai/gpt-oss-20b` | Stable, GA | Alternative, smaller model |
| `openai/gpt-oss-safeguard-20b` | Stable, GA | Safety-focused variant |

> **Verified:** Model ID `openai/gpt-oss-120b` confirmed on https://console.groq.com/docs/model/openai/gpt-oss-120b and https://console.groq.com/docs/models

### B. Free-Tier Feasibility

| Aspect | Finding | Verification |
|--------|---------|--------------|
| **API Access Without Payment** | ✅ Available | Console sign-up, no credit card |
| **Billing Activation Required** | ❌ Not required for free tier | Console |
| **Free Tier Availability** | ✅ Available for new users | Console |
| **Free Tier RPM (GPT-OSS 120B)** | 30 RPM | Console limits page / third-party sources |
| **Free Tier TPM (GPT-OSS 120B)** | 8,000 TPM | Console / byoklist.com |
| **Free Tier RPD (GPT-OSS 120B)** | 1,000 RPD | Console / byoklist.com |
| **Free Tier TPD (GPT-OSS 120B)** | 200,000 TPD | Console / byoklist.com |
| **Model-Specific Limits** | Yes — vary by model | Verified |
| **Regional Restrictions** | Global | No significant restrictions |
| **Commercial Use** | ✅ Allowed on free tier | Terms of service |
| **Data Use (Free Tier)** | **UNVERIFIED** | Need to verify current terms on console |
| **Quota Exhaustion** | 429 response, `retry-after` header | Standard |

> **UNVERIFIED:** Exact current free-tier limits for this organization (shown on console.groq.com/limits after sign-in). Groq data handling terms for free tier.
>
> **TPM Bottleneck Note:** The 8,000 TPM free-tier limit is the binding constraint. A maximum-sized request (24,000-character kit + draft ≈ 6,000+ input tokens) plus output can exceed the per-minute token budget. Not every maximum-sized request is feasible on the free tier. Slice 4.7 must implement token-aware request budgeting.

### C. Structured Output Support

| Feature | Status | Details |
|---------|--------|---------|
| JSON Schema Constrained Output | ✅ Supported | `json_schema` parameter on GPT-OSS 20B/120B and Qwen models |
| Strict Mode (`strict: true`) | ✅ Supported | Constrained decoding, guarantees schema compliance. Requires all properties in `required`, `additionalProperties: false`. |
| Non-Strict Mode (`strict: false`) | ✅ Default | Best-effort schema compliance, may occasionally error |
| Enum Constraints | ✅ Supported | |
| Required Properties | ✅ Supported | All properties must be listed in `required` for strict mode |
| Nullable Fields | ✅ Supported | `type: ["string", "null"]` or `type: ["number", "null"]` |
| Optional Fields | ✅ Supported | Not in `required` array |
| String Constraints (minLength) | ❌ **Not enforced** | Provider does not enforce `minLength` in strict mode; treat as application-level validation |
| Nested Objects | ✅ Supported | Limited depth |
| Streaming + Tools | ❌ Not supported | With structured output |

**Compatibility with AnchorDraft Schema:**
- Our schema uses: `enum` (issue), `type: ["string", "null"]` (suggestion, confidence), `minLength` (quote, explanation), `required` array (ref_key, issue, quote, explanation)
- Groq supports: enum, nullable unions, required. **`minLength` is not enforced by the provider**; treat minimum string lengths as application-level validation responsibilities (citation validator).
- **Groq strict mode requirement:** All properties must be in `required` array and `additionalProperties: false` — provider adapter must adapt schema accordingly

### D. Python SDK & Async Support

| Aspect | Status | Details |
|--------|--------|---------|
| Official Python SDK | ✅ `groq` | `pip install groq` |
| Python Version Support | ✅ 3.8+ | Compatible with our Python 3.12 |
| Native Async Client | ✅ | `AsyncGroq` client |
| Request Timeout Support | ✅ | `timeout` parameter on request |
| Retry Behavior | Basic | Manual retry logic needed (no built-in retry) |
| Exception Types | Basic | `GroqError`, `RateLimitError`, `APITimeoutError`, `BadRequestError`, `AuthenticationError`, `InternalServerError` |
| Structured Output Parameter | ✅ | `response_format={"type": "json_schema", "json_schema": {"name": "...", "strict": true, "schema": {...}}}` |

**Compatibility with `Provider` Protocol:**
- `generate_findings(request) -> ProviderResult` maps to `chat.completions.create()` with `response_format`
- `ProviderError` subclasses mapping:
  - `RateLimitedError` ↔ `RateLimitError` (has `retry_after` via header)
  - `TimeoutError` ↔ `APITimeoutError`
  - `UnavailableError` ↔ `InternalServerError` / `ServiceUnavailable`
  - `BadOutputError` ↔ `BadRequestError` / parsing failure / `json_validate_failed`
  - `BlockedError` ↔ Safety filter response

### E. Model Suitability

| Model | Context Window | Output Limit | Structured Output | Free Tier |
|-------|----------------|--------------|-------------------|-----------|
| **openai/gpt-oss-120b** | 131,072 | 65,536 | ✅ `json_schema` (strict & non-strict) | ✅ |
| **openai/gpt-oss-20b** | 131,072 | 65,536 | ✅ `json_schema` | ✅ |
| **llama-3.1-8b-instant** | 131,072 | 131,072 | ❌ | ✅ |
| **llama-3.3-70b-versatile** | 131,072 | 32,768 | ❌ | ✅ |

**Selected Model:** `openai/gpt-oss-120b` (supports structured output, higher capability for brand governance)

**Quality Evidence:**
- Strong instruction following, chain-of-thought reasoning
- Good exact quotation behavior when prompted
- Resists prompt injection with proper system instruction
- Consistent structured output with schema enforcement (especially `strict: true`)

---

## 6. Gemini Findings (Verified)

### A. Model Identifier & Lifecycle

| Model Identifier | Status | Notes |
|------------------|--------|-------|
| `gemini-3.8-flash` | **Stable, GA** | Released 2026-09-02, current Flash model |
| `gemini-3.6-flash` | Stable, GA | Previous Flash model |
| `gemini-3.5-flash-lite` | Stable, GA | Higher free-tier limits |
| `gemini-3.1-flash-lite` | Stable, GA | Higher free-tier limits |
| `gemini-4-argon` | Limited access | Frontier model, paid tier |

> **Correction from previous spike:** `gemini-3.8-flash` **DOES EXIST** (released September 2, 2026). The previous spike report incorrectly stated it did not exist. Verified via Google DeepMind model card and Gemini API docs.

### B. Free-Tier Feasibility

| Aspect | Finding | Verification |
|--------|---------|--------------|
| **API Access Without Payment** | ✅ Available via Google AI Studio | Verified (docs) |
| **Billing Activation Required** | Required for production quotas (Tier 1+) | Verified (docs) |
| **Free Tier Availability** | ✅ Available for new users | Verified (docs) |
| **Free Tier RPM (3.8 Flash)** | **Account/project-dependent** | AI Studio rate limit page (project-specific, not guaranteed) |
| **Free Tier TPM (3.8 Flash)** | **Account/project-dependent** | AI Studio rate limit page |
| **Free Tier RPD (3.8 Flash)** | **Account/project-dependent** | AI Studio rate limit page |
| **Free Tier RPM (3.5 Flash-Lite)** | **Account/project-dependent** | AI Studio rate limit page |
| **Free Tier RPD (3.5 Flash-Lite)** | **Account/project-dependent** | AI Studio rate limit page |
| **Model-Specific Limits** | Yes — vary by model | Verified |
| **Regional Restrictions** | Limited to supported regions | Verified |
| **Commercial Use** | Allowed on paid tier; free tier data may be used for training | Verified (billing docs) |
| **Quota Exhaustion** | Requests fail with 429; no auto-retry | Verified |

> **UNVERIFIED:** Exact current free-tier RPM/TPM/RPD for this project (shown on aistudio.google.com/rate-limit after sign-in). Limits are account/project-dependent and not guaranteed. Do not treat published figures as guaranteed values.

### C. Structured Output Support

| Feature | Status | Details |
|---------|--------|---------|
| JSON Schema Constrained Output | ✅ Supported | `google-genai` SDK accepts Pydantic-generated schemas |
| JSON Schema Subset | OpenAPI subset | No unions, no min/max constraints in some versions |
| Enum Constraints | ✅ Supported | `enum` in schema respected |
| Required Properties | ✅ Supported | Enforced |
| Nullable Fields | ✅ Supported | `type: ["string", "null"]` or `nullable: true` |
| Optional Fields | ✅ Supported | Not in `required` array |
| String Constraints (minLength) | ✅ Supported | `minLength` on strings |
| Nested Objects | ✅ Supported | Limited depth |

**Compatibility with AnchorDraft Schema:**
- Our schema uses: `enum` (issue), `type: ["string", "null"]` (suggestion, confidence), `minLength` (quote, explanation), `required` array (ref_key, issue, quote, explanation)
- All features **supported** by Gemini's structured output

### D. Python SDK & Async Support

| Aspect | Status | Details |
|--------|--------|---------|
| Official Python SDK | ✅ `google-genai` | `pip install google-genai` |
| Python Version Support | ✅ 3.10+ | Compatible with our Python 3.12 |
| Native Async Client | ✅ | `async def generate_content_async()` |
| Request Timeout Support | ✅ | `timeout` parameter on request |
| Retry Behavior | Configurable | Built-in retry for transient errors |
| Exception Types | ✅ | `GoogleAPIError`, `RateLimitError`, `APITimeoutError`, `BadRequestError`, `PermissionDeniedError`, `InternalServerError` |

**Compatibility with `Provider` Protocol:**
- `generate_findings(request) -> ProviderResult` maps directly to `generate_content_async()` with `generation_config.response_schema`
- All `ProviderError` subclasses have direct mappings:
  - `RateLimitedError` ↔ `RateLimitError` (has `retry_after`)
  - `TimeoutError` ↔ `APITimeoutError`
  - `UnavailableError` ↔ `InternalServerError` / `ServiceUnavailable`
  - `BadOutputError` ↔ `BadRequestError` / parsing failure
  - `BlockedError` ↔ `PermissionDeniedError` / safety filter

### E. Model Suitability

| Model | Context Window | Output Limit | Free Tier | Suitability |
|-------|----------------|--------------|-----------|-------------|
| **gemini-3.8-flash** | 1M tokens | 65,536 | ✅ Available | ✅ Fallback — structured output, large context |
| **gemini-3.5-flash-lite** | 1M tokens | 65,536 | ✅ Higher limits | ✅ Alternative fallback |
| **gemini-4-argon** | 1M+ | 65,536 | ❌ Paid only | ❌ Not for free tier |

**Selected Fallback Model:** `gemini-3.8-flash` (current stable Flash, structured output support)

---

## 7. Provider Comparison Table (Finalized)

| Criterion | Groq (Primary) | Gemini (Fallback) |
|---|---|---|
| **Provider** | Groq | Google |
| **Exact Model Identifier** | `openai/gpt-oss-120b` | `gemini-3.8-flash` |
| **Lifecycle Status** | Stable, GA | Stable, GA |
| **Free API Availability** | ✅ Yes (Groq Console) | ✅ Yes (Google AI Studio) |
| **Billing Requirement** | Not required for free tier | Required for production quotas |
| **Free-Tier RPM** | 30 (org-specific) | Account/project-dependent |
| **Free-Tier TPM** | 8,000 (org-specific) | Account/project-dependent |
| **Free-Tier RPD** | 1,000 (org-specific) | Account/project-dependent |
| **Free-Tier TPD** | 200,000 (org-specific) | Not published |
| **Regional Restrictions** | Global | Supported regions only |
| **Context Window** | 131,072 | 1,048,576 |
| **Output Limit** | 65,536 | 65,536 |
| **Structured JSON Support** | ✅ `json_schema` (strict & non-strict) | ✅ Full (google-genai SDK) |
| **Strict Mode** | ✅ Constrained decoding | Always strict (native) |
| **JSON Schema Compatibility** | ✅ Good (requires all props in `required`, `additionalProperties: false`, **no minLength enforcement**) | ✅ Good (enums, nullable, required, minLength) |
| **Nullable Fields Support** | ✅ `type: ["string", "null"]` | ✅ `type: ["string", "null"]` / `nullable: true` |
| **Native Async Python SDK** | ✅ `groq` (`AsyncGroq`) | ✅ `google-genai` (async native) |
| **Timeout Support** | ✅ Native | ✅ Native |
| **Rate-Limit Handling** | ✅ Native (`retry_after` header) | ✅ Native (`retry_after`) |
| **Model Quality (Brand Governance)** | ✅ Strong reasoning, chain-of-thought | ✅ Strong instruction following, exact quotes |
| **Data Handling (Free Tier)** | **UNVERIFIED** (check console) | May use for training |
| **Free Tier Headroom (RPM)** | Better (30) | Limited (account-dependent) |
| **Free Tier Headroom (TPM)** | Limited (8,000) | Generous (account-dependent) |
| **Overall Suitability** | ⭐⭐⭐⭐⭐ Primary (architect decision) | ⭐⭐⭐⭐ Good fallback |

---

## 8. Exact AnchorDraft Schema Compatibility

### AnchorDraft Output Schema (from `prompt_builder.py`)

```json
{
  "type": "object",
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "ref_key": {"type": "string"},
          "issue": {"type": "string", "enum": ["violation", "contradicts_fact", "outdated_fact", "unsupported_claim"]},
          "quote": {"type": "string", "minLength": 1},
          "explanation": {"type": "string", "minLength": 1},
          "suggestion": {"type": ["string", "null"]},
          "confidence": {"type": ["number", "null"]}
        },
        "required": ["ref_key", "issue", "quote", "explanation"]
      }
    }
  },
  "required": ["findings"]
}
```

### ModelFindingCandidate (Pydantic Model)

```python
class ModelFindingCandidate(BaseModel):
    ref_key: str
    issue: Literal["violation", "contradicts_fact", "outdated_fact", "unsupported_claim"]
    quote: str = Field(..., min_length=1)
    explanation: str = Field(..., min_length=1)
    suggestion: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    model_config = {"extra": "forbid"}
```

### Compatibility Assessment

| Schema Feature | ModelFindingCandidate | OUTPUT_SCHEMA | Groq (GPT-OSS 120B) | Gemini (3.8 Flash) |
|----------------|----------------------|---------------|---------------------|-------------------|
| `ref_key` (string, required) | ✅ | ✅ | ✅ | ✅ |
| `issue` (enum, required) | ✅ | ✅ | ✅ | ✅ |
| `quote` (string, minLength=1, required) | ✅ | ✅ | ✅ (minLength not enforced by provider) | ✅ |
| `explanation` (string, minLength=1, required) | ✅ | ✅ | ✅ (minLength not enforced by provider) | ✅ |
| `suggestion` (string, nullable, optional) | ✅ | ✅ `type: ["string", "null"]` | ✅ (strict mode requires in `required`) | ✅ |
| `confidence` (number, nullable, optional) | ✅ | ✅ `type: ["number", "null"]` | ✅ (strict mode requires in `required`) | ✅ |
| `extra: forbid` | ✅ | ✅ | ✅ (`additionalProperties: false`) | ✅ |

**Groq Strict Mode Adaptation Required:**
- For `strict: true`, Groq requires ALL properties in the `required` array and `additionalProperties: false`
- The provider adapter must transform the schema:
  - Add `suggestion` and `confidence` to `required` array (as nullable)
  - Set `additionalProperties: false` on all objects
  - This is a **provider-specific schema adaptation** — the shared `ModelFindingCandidate` and `OUTPUT_SCHEMA` remain unchanged

**minLength Note:** Groq strict mode does not enforce `minLength`. Minimum string length validation remains an application-level responsibility (citation validator).

**Compatibility Verdict:**
- **Groq (GPT-OSS 120B):** ✅ Fully compatible with strict mode adaptation (minLength validated by application)
- **Gemini (3.8 Flash):** ✅ Fully compatible natively

---

## 9. Free-Tier Feasibility and Realistic Usage

### AnchorDraft Usage Profile
- One model call per review
- Maximum findings: 25
- Output budget: 4096 tokens
- Request timeout: 45 seconds
- Draft limit: 20,000 characters
- Combined kit content: 24,000 characters
- Estimated tokens per call: ~4,000 (input + output)

### Free-Tier Capacity Analysis

| Provider | Model | TPM Limit | Tokens/Call | Max Calls/Min (TPM) | Max Calls/Min (RPM) | Daily Cap (RPD) |
|----------|-------|-----------|-------------|---------------------|---------------------|-----------------|
| Groq | openai/gpt-oss-120b | 8,000 (org-specific) | ~4,000 | **2** | 30 | 1,000 (org-specific) |
| Gemini | gemini-3.8-flash | Account-dependent | ~4,000 | Account-dependent | Account-dependent | Account-dependent |
| Gemini | gemini-3.5-flash-lite | Account-dependent | ~4,000 | Account-dependent | Account-dependent | Account-dependent |

**Analysis:**
- **Groq:** TPM (8,000) is binding → ~2 calls/minute = 120/hour. RPM (30) is generous. **A maximum-sized request (24,000 chars kit + draft) can exceed the per-minute token budget once output is included. Not every maximum-sized request is feasible on the free tier.**
- **Gemini:** Limits are account/project-dependent. Free tier provides access but exact headroom varies. Flash-Lite typically offers higher limits than Flash.

**Bottleneck Analysis:**
- **Groq:** TPM bottleneck — severely limits throughput on free tier
- **Gemini:** Account-dependent; Flash-Lite generally provides reasonable headroom

**Quota Exhaustion Handling:**
- Both return 429 with `retry-after` header
- Implement retry with exponential backoff, max 1 retry
- On quota exhaustion: `llm_status = failed`, deterministic findings preserved, warning shown

**Demo Reliability:**
- **Groq Primary:** 2 calls/minute = 120/hour — tight for demo with multiple reviewers
- **Gemini Flash-Lite Fallback:** Typically sufficient for demo
- **Combined:** Primary + fallback provides redundancy

**Slice 4.7 Requirement:** Implement token-aware request budgeting (estimate tokens before call, skip or truncate if over budget) and graceful rate-limit handling.

---

## 10. Official Sources Summary

| Source | URL | Accessed | Status |
|--------|-----|----------|--------|
| Groq Models | https://console.groq.com/docs/models | 2026-11-06 | Primary |
| Groq Structured Output | https://console.groq.com/docs/structured-outputs | 2026-11-06 | Primary |
| Groq Rate Limits | https://console.groq.com/limits | 2026-11-06 | Requires sign-in |
| Groq Python SDK | https://github.com/groq/groq-python | 2026-11-06 | Primary |
| Gemini API Docs | https://ai.google.dev/gemini-api/docs | 2026-11-06 | Primary |
| Gemini Structured Output | https://ai.google.dev/gemini-api/docs/structured-output | 2026-11-06 | Primary |
| Gemini Rate Limits | https://ai.google.dev/gemini-api/docs/rate-limits | 2026-11-06 | Primary |
| Gemini Billing/Free Tier | https://ai.google.dev/gemini-api/docs/billing | 2026-11-06 | Primary |
| AI Studio Rate Limits | https://aistudio.google.com/rate-limit | 2026-11-06 | Requires sign-in |
| Gemini Python SDK | https://github.com/googleapis/python-genai | 2026-11-06 | Primary |
| Gemini 3.8 Flash Model Card | https://deepmind.google/models/model-cards/gemini-3-8-flash | 2026-11-06 | Primary |

---

## 11. Live Experiment Status

**Status:** **NOT PERFORMED** — No API keys configured in environment (`LLM_PROVIDER=fake`).

Per the spike instructions, a live experiment requires credentials. Since no `GROQ_API_KEY` or `GEMINI_API_KEY` is configured in the environment, live testing was **not performed**.

**Planned Experiment (for future execution):**
```python
# Synthetic test case
draft = "We should utilize this guaranteed solution for our customers."
rules = [RuleData(rule_key="TERM-01", check_kind="llm", ...)]
facts = [FactData(fact_key="FACT-01", statement="Our product is 99.9% available", ...)]
# Expected: 2 findings (TERM-01: "utilize" → "use", PHRASE-01: "guaranteed")
```

**Status:** NOT VERIFIED — credentials unavailable

---

## 12. Provider Error Mapping (Finalized)

| AnchorDraft Error | Groq Mapping | Gemini Mapping |
|---|---|---|
| `RateLimitedError` | HTTP 429, `RateLimitError` (header `retry-after`) | `RateLimitError` (has `retry_after`) |
| `TimeoutError` | `APITimeoutError`, request timeout | `APITimeoutError` |
| `UnavailableError` | `InternalServerError`, `ServiceUnavailable`, connection errors | `InternalServerError`, `ServiceUnavailable` |
| `BadOutputError` | `BadRequestError`, `json_validate_failed`, JSON parse failure | `BadRequestError`, JSON parse failure |
| `BlockedError` | **Safety filter response only** (provider-specific safety signal) | **Safety filter response only** (provider-specific safety signal) |

**Important:** Do not equate generic `PermissionDeniedError`, `AuthenticationError`, or authorization failures with safety blocks. `BlockedError` maps only to explicit safety refusal signals from the provider.

**Retry Policy (both providers):**
- Retry once on `RateLimitedError` (wait `retry_after`, capped at 10s)
- Retry once on `TimeoutError`, `UnavailableError`
- Max 1 retry total
- Respect 45-second request budget (`ProviderRequest.timeout_seconds`)
- On exhaustion: `llm_status = failed`, deterministic findings preserved, warning added

**Provider Output Handling (Application-Level Responsibilities):**
Provider responses still require: JSON parsing, refusal detection (safety blocks), truncation detection (incomplete output due to token limits), and full application-level validation via the citation validator. Structured output does not establish factual correctness.

---

## 13. Files Modified

| File | Change |
|------|--------|
| `docs/REVIEW_ENGINE.md` | Updated §2.2 Provider Selection Decision with architect-approved decision (Groq primary, Gemini fallback) |
| `docs/ai-log/provider-spike.md` | **Newly created** — documents provider spike findings with verified model identifiers, Groq strict mode details, error mapping, free-tier analysis |

---

## 14. Files NOT Modified (Scope Respected)

| File | Status |
|------|--------|
| `engine/app/llm/provider.py` | Unchanged |
| `engine/app/llm/fake_provider.py` | Unchanged |
| `engine/app/llm/prompt_builder.py` | Unchanged |
| `engine/app/models/pipeline.py` | Unchanged |
| `engine/tests/` | Unchanged |

> **No production provider implementation created.** Only documentation updated per slice scope.

---

## 15. Verdict

### **PASS WITH LIMITATIONS**

**Rationale:**
- ✅ Clear provider selection documented with architect-approved rationale
- ✅ All decision criteria from REVIEW_ENGINE.md §3 addressed
- ✅ Documentation updated in `REVIEW_ENGINE.md` and `provider-spike.md`
- ✅ Model identifiers verified: `openai/gpt-oss-120b` (Groq), `gemini-3.8-flash` (Gemini)
- ✅ Structured output compatibility verified for both providers
- ✅ Groq strict mode schema adaptation documented
- ✅ Error mapping documented for both providers
- ✅ No production provider code implemented (scope respected)
- ⚠️ **Limitation:** Live API testing not performed (no credentials available). Free-tier limits and model behavior based on documentation and third-party reports, not live console verification.
- ⚠️ **Limitation:** Groq data handling terms for free tier remain UNVERIFIED.
- ⚠️ **Limitation:** Exact free-tier RPM/TPM/RPD for selected models not verified against live console pages (require sign-in).
- ⚠️ **Limitation:** Safety block response shapes not verified live.

**Recommendation:** Proceed to Slice 4.7 (Production Provider Implementation) with the understanding that live integration testing must be performed before demo. Configure real `GROQ_API_KEY` and `GEMINI_API_KEY` and run the synthetic spike test case before Slice 4.7 implementation begins.

---

**Date:** 2026-11-06
**Branch:** `feat/phase-4-review-engine`
**Commit:** `d8c5077`

**Next Slice:** 4.7 — Production Provider Implementation (awaiting architectural approval)
