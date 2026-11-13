# AI Log

## 2026-11-04 â€” Slice 0: Repository Skeleton & Hello-World Pipeline

**Architect:** Siddhartha
**Duration:** ~2 hours

### Summary

Created the complete monorepo structure and hello-world pipeline for both services per ARCHITECTURE.md section 5.1 and 5.3 Slice 0.

### Files Created

#### Repository Structure
- `docs/ai-log/` - AI log and decisions
- `supabase/migrations/` - Database migrations (README only for now)
- `engine/app/{api,auth,pipeline,checks,llm,validator,store,models}` - FastAPI modules
- `engine/tests/` - Pytest tests
- `web/src/features/{auth,kits,drafts,findings,approvals,insights}` - React feature folders
- `web/src/lib`, `web/src/components` - Shared code

#### Engine (FastAPI)
- `engine/pyproject.toml` - Dependencies pinned from PyPI (fastapi 0.162.0, uvicorn 0.54.0, pydantic 2.14.2, python-dotenv 1.2.4, pytest 9.2.0, pytest-asyncio 1.4.0, httpx 0.28.1)
- `engine/app/main.py` - FastAPI app with CORS (from ALLOWED_ORIGINS, no wildcard) and X-Request-Id middleware
- `engine/app/core/config.py` - Pydantic Settings configuration
- `engine/app/api/health.py` - GET /v1/health returning {status, version, time}
- `engine/app/api/middleware.py` - X-Request-Id middleware (generates UUID if not provided)
- `engine/tests/test_health.py` - 3 tests: health returns ok, returns request ID, uses provided request ID
- `engine/.env.example` - Environment variable names only

#### Web (Vite + React 19 + TypeScript + Tailwind CSS 4)
- `web/package.json` - Dependencies pinned from npm (react 19.3.1, vite 8.3.5, @vitejs/plugin-react 6.1.2, tailwindcss 4.3.4, typescript 7.0.2, vitest 3.1.1)
- `web/vite.config.ts` - Vite config with React plugin, Tailwind plugin, proxy to engine
- `web/tsconfig.json`, `web/tsconfig.node.json` - Strict TypeScript config
- `web/src/main.tsx`, `web/src/App.tsx` - App entry point
- `web/src/index.css` - Tailwind CSS 4 import
- `web/src/features/health/HealthCheck.tsx` - Component that calls GET /v1/health with loading/error/success states
- `web/.env.example` - Environment variable names only

#### Root Files
- `.gitignore` - Excludes node_modules, .env, build outputs, IDE files
- `README.md` - Project overview, quick start, deployment instructions
- `docs/DISCLOSURE.md` - All libraries, services, templates disclosed
- `docs/ai-log/decisions.md` - Decision log (initialized)
- `docs/ai-log/log.md` - This file

### Key Decisions Recorded

See `docs/ai-log/decisions.md`.

### Prompts Used

1. Read all specification documents (AGENTS.md, ARCHITECTURE.md, DATA_MODEL.md, API_CONTRACT.md, REVIEW_ENGINE.md)
2. Create plan for Slice 0 and wait for approval
3. Implement monorepo layout per ARCHITECTURE.md Â§5.1
4. Implement FastAPI engine with health endpoint, middleware, CORS, pytest test
5. Implement Vite/React/TypeScript/Tailwind web app with health check page
6. Create all required documentation and config files
7. Verify: pytest passes, web builds, engine runs, page displays health result

### Architect Changes/Reviews

- Plan approved without changes
- All dependency versions verified against real package indexes (PyPI, npm)

### How It Works (5 bullets)

1. **Engine starts**: `uvicorn app.main:app` loads FastAPI app with CORS middleware (origins from `ALLOWED_ORIGINS`, no wildcard) and X-Request-Id middleware
2. **Health endpoint**: GET `/v1/health` returns `{status: "ok", version, time}` in UTC ISO format
3. **Request ID flow**: Middleware generates UUID if `X-Request-Id` header absent, echoes it back in response headers and request state
4. **Web dev server**: Vite serves React app on `:5173`, proxies `/v1/*` to engine on `:8000` to avoid CORS during development
5. **HealthCheck component**: On mount, calls `VITE_ENGINE_URL/v1/health` with generated `X-Request-Id`, shows loading spinner, then success card or error message

### Git Log

```
bace544 chore: slice 0 - repository skeleton and hello-world pipeline
```

### Risks (Honest)

1. **No database yet** - Supabase migrations and RLS not implemented (Slice 1)
2. **No authentication** - JWT verification and Supabase Auth not wired (Slice 1)
3. **No real LLM integration** - Using fake provider; provider spike needed (Slice 4)
4. **CORS testing limited** - Test client doesn't fully exercise preflight; production CORS needs verification
5. **Single commit** - All Slice 0 work in one commit; future slices should use smaller, reviewable commits per AGENTS.md Â§4

---

## 2026-11-05 â€” Slice 0: Corrections & Verification

**Architect:** Siddhartha
**Duration:** ~3 hours

### Summary

Fixed and verified Slice 0 implementation per review feedback. Addressed CORS configuration parsing, added missing engine README, updated AI log, verified dependency disclosures, and ran full test suites.

### Changes Made

#### A. Engine CORS Configuration (ALLOWED_ORIGINS parsing)
- **Problem**: `ALLOWED_ORIGINS` declared as `list[str]` but `.env.example` used comma-separated values; pydantic expects JSON arrays for complex types.
- **Solution**: Changed field to string type with custom property `ALLOWED_ORIGINS_LIST` that parses both JSON array and comma-separated formats. Added `_parse_allowed_origins()` helper function.
- **Files changed**: `engine/app/core/config.py`, `engine/app/main.py`, `engine/.env.example`, `engine/tests/conftest.py`, `engine/tests/test_health.py`
- **Tests added**: 5 new tests for comma-separated format (`TestCORSCommaSeparated` class)

#### B. Engine README
- **Problem**: `pyproject.toml` referenced `README.md` but `engine/README.md` was missing.
- **Solution**: Created `engine/README.md` with quick start, configuration, tests, API, CORS, and deployment docs.

#### C. AI Usage Log Update
- Updated this log to reflect actual implementation milestones and corrections.

#### D. AI Disclosure & Dependency Inventory
- Verified `docs/DISCLOSURE.md` and `docs/VERSION_SOURCES.md` match actual `pyproject.toml`, `package.json`, and lockfiles.
- All versions confirmed from official package indexes (PyPI, npm) on 2026-11-04.
- No unverified versions or licenses found.

#### E. Agent Instruction Discoverability
- Recommended adding root-level `AGENTS.md` pointing to `docs/AGENTS.md` as authoritative source.

#### F. Architecture Decision Status
- **Conflict found**: ARCHITECTURE.md revision text says "decisions 1 to 9 confirmed" but decision table shows decisions 1-9 as "PROPOSED" (except decision 9 = "DECIDED"). Flagged for architect review.

#### G. CI Recommendation
- No CI workflow exists. Recommended adding minimal GitHub Actions workflow running engine tests and web build/test.

### Commands Actually Executed

```bash
# Engine
cd engine
pip install -e ".[test]"
python -m pytest tests/ -v
# â†’ 14 passed (9 original + 5 new comma-separated tests)

# Web
cd web
npm ci
npm run test
# â†’ 7 passed
npm run build
# â†’ success (223 KB JS, 9 KB CSS gzipped)

# Engine health endpoint verification
uvicorn app.main:app --port 8000
curl http://localhost:8000/v1/health
# â†’ {"status":"ok","version":"0.1.0","time":"..."}
```

### Test/Build Results

| Check | Result |
|-------|--------|
| Engine install (`pip install -e ".[test]"`) | âœ… Success |
| Engine tests (`pytest`) | âœ… 14 passed |
| Web install (`npm ci`) | âœ… Success |
| Web tests (`npm run test`) | âœ… 7 passed |
| Web build (`npm run build`) | âœ… Success (223 KB JS, 9 KB CSS) |
| Engine health endpoint | âœ… Returns `{status, version, time}` |
| CORS preflight (JSON array origins) | âœ… 200 with correct headers |
| CORS preflight (comma-separated origins) | âœ… 200 with correct headers |
| X-Request-Id middleware | âœ… Generated/echoed correctly |
| No secrets in tracked files | âœ… Verified |

### Deployment Status

| Target | Status | Notes |
|--------|--------|-------|
| Vercel (Web) | Not deployed | Requires Vercel project creation and env vars |
| Render (Engine) | Not deployed | Requires Render service creation and env vars |
| Supabase | Not created | Requires Supabase project creation |

### Remaining Blockers

1. **Architecture decision status conflict** â€” Needs architect to confirm which decisions are actually DECIDED vs PROPOSED.
2. **No CI pipeline** â€” Recommended but not required for Slice 0.
3. **External service credentials** â€” Vercel, Render, Supabase require human setup; no secrets in repo.

### Recommended Next Action

1. Architect reviews and resolves decision status in ARCHITECTURE.md.
2. Human creates Vercel/Render/Supabase projects and configures env vars.
3. Proceed to Slice 1 (Schema, auth, roles, RLS) after approval.


## 2026-11-12 â€” Improvement 2 Integration Hardening Follow-up

### Summary

Traced the reported Start Review no-response regression against the deployed staging service. Render request logs showed that the browser had reached `POST /v1/reviews/preview`, which returned HTTP 422. The previous frontend error parser did not understand FastAPI's array-shaped validation details, and the error was only placed in the page-level toast. The UI now renders preview failures directly beside the Start Review control and translates FastAPI validation details into a readable message.

### Changes

- Updated `web/src/lib/data.ts` to extract FastAPI request-validation locations and messages from `detail[]`, preserving a machine-readable `request_validation_error` reason.
- Updated `ContentDetail` to show preview failures inline in the Review Status panel; the button retains immediate pending feedback and is disabled while the request is in flight.
- Added frontend tests for FastAPI 422 parsing and inline preview failure visibility.
- Configured the **staging Render service only** to select Gemini as its primary provider (`LLM_PROVIDER=gemini`, model `gemini-3.8-flash`). Disabled provider fallback because only the Gemini credential was confirmed for this staging configuration; no second provider credential was assumed. No secret values were read or written to the repository.

### Verification

- Engine: `py -3.12 -m pytest tests -q` â€” **702 passed, 4 skipped, 2 warnings**.
- Web: `npm test -- --reporter=dot` â€” **183 passed**.
- Web: `npm run build` â€” succeeded; existing Vite dynamic-import warning remains.
- Provider factory smoke test with a non-secret placeholder credential and staging environment â€” instantiated `GeminiProvider` with model `gemini-3.8-flash`; this verifies provider selection, not the real API credential.
- Render staging `/v1/health?deep=1` â€” `status=ok`, database connected.
- Render CORS preflight for the current Vercel branch alias â€” HTTP 200 with the exact allow-origin and required headers.
- Vercel branch deployment for commit `d6fb3e1` â€” READY and assigned to the branch alias.

### Not Yet Verified

- The exact cause inside the earlier HTTP 422 response was not retained in Render logs. The frontend now exposes FastAPI's validation details on the next request; an authenticated browser retest is still required to capture and resolve any underlying request-shape issue.
- No authenticated preview â†’ consent â†’ confirmation â†’ Gemini provider call was executed in this pass. Real provider acceptance, returned findings, and audit rows remain end-to-end checks, not claimed as complete.
- Visual asset upload â†’ vision analysis â†’ visual findings and UI rendering remain end-to-end checks. Automated visual and confidentiality suites pass, but this does not replace a live workflow test.


## 2026-11-12 â€” Start Review Silent No-op Guard

### Finding and change

The review-start handler contained a silent early return when `latestRevision?.id` was unavailable: `if (!targetRevisionId || startingReviewRef.current) return`. The button could therefore be visible and clickable while the handler returned without setting loading state, showing an error, or making a request. This is a concrete no-op path consistent with the reported symptom; the screenshot alone does not prove it was the only runtime cause for the user's particular content record.

The handler now resolves the target revision from the explicitly selected revision first, then the selected revision object, then the latest loaded revision. If none exists, it sets a visible inline error and releases the loading/duplicate-submission guard rather than silently returning. A regression test covers the no-revision path.

### Verification

- `npm run test -- --reporter=dot src/features/contents/ContentDetail.test.tsx` â€” 22 passed.
- `npm run build` â€” succeeded; existing Vite dynamic-import warning remains.
- Full web suite `npm test -- --reporter=dot` â€” 184 passed across 11 files. Existing nested-anchor React warnings remain in unrelated landing-page tests.
- `git diff --check` â€” passed.
- Commit `781f7d9 fix: prevent silent review start no-op` pushed to `feat/confidentiality-aware-processing`.
- Vercel Preview deployment for `781f7d9` â€” READY; branch alias points to this deployment.

### Limitation

No authenticated browser automation/session is available in this pass to prove pointer hit-testing and click delivery in the user's browser. The no-revision silent-return path is fixed and regression-tested; a live retest is still needed to confirm the user's exact record now reaches the preview API.


## 2026-11-12 â€” Root Cause Fix: Latest Revision Identifier Contract

### Root cause

The `v_latest_revision` view exposes the revision primary key as `revision_id` (see `supabase/migrations/20261104000006_views.sql`), while `getLatestRevision()` returned that row directly as the `Revision` interface, whose primary-key field is `id`. `ContentDetail.loadContent()` then assigned `revisionIdRef.current = rev?.id ?? null` and `latestRevision = rev`; therefore a content item with revisions could render its body/version but still have no usable `latestRevision.id`, causing Start Review to report that no revision was loaded.

### Fix

Changed `getLatestRevision()` to query the base `revisions` table ordered by descending version and limited to one row. This returns the canonical full `Revision` shape and avoids maintaining a fragile view-to-Revision field mapping. Added tests for the canonical `id` contract and the no-revisions case.

### Verification

- Targeted data + ContentDetail tests: **100 passed**.
- Full frontend suite: **186 passed across 11 files**.
- Frontend production build: succeeded; pre-existing Vite dynamic-import warning remains.
- `git diff --check`: passed.

### Scope

This fixes the frontend revision-loading contract shared by both Improvement 1 and Improvement 2 workflows. It does not bypass review authorization, preview confirmation, confidentiality policy checks, or image consent.


## 2026-11-12 â€” Preview API 500: Normalize Fact Expiry Dates

### Production-like failure found from Render logs

The user's authenticated `POST /v1/reviews/preview` reached `build_review_preview()` and failed while building the text provider request. Render traceback identified:

`TypeError: '>=' not supported between instances of 'str' and 'datetime.date'`

Supabase returns the `approved_facts.valid_until` DATE column as an ISO date string, but `FactData.valid_until` is consumed as a Python `date`. `SupabaseDataLoader.load_rules_and_facts()` had passed the string through unchanged. This crashed preview generation before any Gemini/provider request. The browser's CORS error was secondary to the HTTP 500 response; the earlier successful CORS preflight did not validate the failing POST path.

### Fixes

- Normalize non-null ISO `valid_until` strings to `datetime.date` in `SupabaseDataLoader.load_rules_and_facts()` at the Supabase boundary. Preserve `None` for non-expiring facts and already-decoded date objects.
- Added regression coverage proving ISO date strings are parsed and non-expiring facts remain `None`.
- Changed `getLatestReviewForRevision()` to use Supabase `maybeSingle()` for the expected no-review-yet case. This removes the noisy HTTP 406 response generated by `.single()` when a revision has no reviews.
- Replaced malformed manually copied GitHub SVG path data in both the router and its test fixture with a valid canonical path. This addresses the browser's SVG `path d: Expected number` warning.

### Verification

- Full backend: **703 passed, 4 skipped, 2 warnings**.
- Full frontend: **187 passed across 11 files**.
- Frontend production build: succeeded; existing ineffective dynamic-import warning remains.
- `git diff --check`: passed.

### Remaining live verification

The code fix is verified locally, but a new Render staging deployment and an authenticated Preview â†’ confirm â†’ Gemini processing run are still required to prove the live pipeline. Permissions-Policy feature warnings are emitted by the hosted response headers/browser compatibility and are not the cause of the preview failure.


## 2026-11-12 â€” Background Pipeline KeyError: Include Review Requester in Preview Query

### Root cause

The user's first live confirmed review reached the background pipeline and failed with `KeyError`. `ReviewOrchestrator._load_confirmed_preview()` selected only `p.*` from `review_previews`, but `run_pipeline()` then validated ownership using `preview_record["review_requested_by"]`. The parent review's `requested_by` field was never selected, so the dictionary lookup failed deterministically after confirmation.

### Fix

- Updated the confirmed-preview query to select `p.*` plus `r.requested_by AS review_requested_by` from the joined parent review.
- Added a regression test asserting that the selected row contract includes `review_requested_by` and that the join is present.
- Changed the top-level `pipeline_failed` logger to `logger.exception()` so future unexpected pipeline failures include a traceback while preserving the existing safe, type-only error returned to users. No prompt, source text, PII, image bytes, or reverse map is logged.

### Verification

- Focused orchestrator suite: **19 passed, 4 skipped**.
- Full backend suite: **704 passed, 4 skipped, 2 warnings**.
- The previous staging build is live on Render; this fix still requires a new deployment and another real confirmed review to verify provider processing and persisted findings.

### State checkpoint

As of this entry, Improvement 2's live path has successfully completed `POST /v1/reviews/preview` (201 Created) and `POST /v1/reviews/confirm` (202 Accepted) on staging. The confirmed background job then failed on the missing requester field above. The prior date-string normalization fix is already live. Preserve this working preview/confirmation path; do not replace it with a direct review-start path or bypass consent, policy, or preview integrity checks.


## 2026-11-12 ? Creator Image Upload UI for Visual Brand Compliance

### Implementation

- Added an **Upload images** section to the content detail page for creators/owners, associated with the latest revision only (the review engine only processes the latest revision).
- Supports selecting multiple PNG, JPEG/JPG, and WebP files, uploaded sequentially to the existing `POST /v1/imports/visual` endpoint.
- Added a typed frontend API client using authenticated multipart `FormData`, preserving the browser-generated multipart boundary and carrying `content_id` plus `revision_id`.
- Client checks empty files, the 10 MB per-image limit, and actual PNG/JPEG/WebP file signatures before upload; it does not trust filename extensions alone.
- Shows per-file progress/errors and thumbnails from short-lived signed URLs after successful upload.
- Pauses uploads for historical revision selections and while a review is queued/running. Successful attachment clears the prior review presentation so a fresh privacy preview/consent step is required.
- Upload does not trigger provider processing or image consent. Existing preview/confirmation safeguards remain the only route to send original image bytes to a vision provider.
- Reuses the existing backend upload pipeline, which validates image bytes, strips image metadata, writes to private Supabase Storage, records integrity metadata, and associates the asset with the content revision.

### Verification

- Frontend full suite: **194 passed across 11 files**.
- Targeted upload/data + ContentDetail tests: **108 passed**.
- `npm run build`: succeeded; existing Vite ineffective dynamic-import warning remains.
- `git diff --check`: passed.

### Scope and limitations

- Supported image formats deliberately match the backend and visual asset service: PNG, JPEG, WebP. GIF/SVG are not accepted by the existing visual-analysis storage pipeline.
- The upload section shows previews uploaded during the current page session. Previously linked images remain visible in the review privacy preview; a persistent asset gallery/list endpoint is not part of this UI addition.
- No backend code or database migration was changed in this upload UI slice.


## 2026-11-12 â€” Review Confirmation 409: Stale Asset Manifest + Hidden UI Error

### Live root cause confirmed from staging database and Render request logs

The latest preview was created at `2026-11-11 20:25:33.847544+00` with an empty `asset_manifest` (`[]`, zero assets). The PNG was successfully uploaded and linked to the same revision at `20:25:36.934938+00`. Confirmation attempts began at `20:25:40.831221+00` and repeatedly returned HTTP 409.

`confirm_review_preview()` intentionally re-queries the revision's visual-asset associations and compares them to the frozen preview manifest. Because the new image was linked after preview creation, `current_ids != preview_asset_ids` and the endpoint correctly raises `assets_changed`. The preview row remained unconsumed. This is expected integrity enforcement, not a provider/Gemini failure.

### Frontend defect and correction

The confirm handler previously sent all unknown errors to the page-level toast. The toast is behind the open modal, so the user saw the click animation but no actionable error. Also, a successful upload now explicitly clears any stale preview state and image consent.

Changes:
- Invalidate the preview token and image consent after any successful upload.
- Handle known stale-preview reasons (`assets_changed`, `asset_changed`, `revision_changed`, `not_latest_revision`, `revision_not_editable`, `active_kit_changed`, `kit_changed`, `policy_changed`, `preview_integrity_failed`, `preview_not_available`) by closing the stale dialog and showing actionable guidance to prepare a fresh preview.
- Keep unexpected confirmation/network/server errors visible inside the preview dialog via a modal-local alert instead of a toast hidden behind it.
- Existing `preview_expired` and `preview_already_consumed` handling remains, with modal closure and review status refresh as appropriate.
- Added regression tests for stale image-manifest conflicts and visible unexpected confirmation failures.

### Verification

- Frontend suite: **196 passed across 11 files**.
- Frontend production build: succeeded; existing ineffective dynamic-import warning remains.
- `git diff --check`: passed.
- No backend or database changes were required for this issue.

## 2026-11-12 - Guideline-Gap Analytics Completion and Audit Refinements

### Implementation refinements

- Restricted historical evidence to completed reviews only, while retaining latest-decision-per-finding and exact current guideline-text matching.
- Grouped unrelated/singleton dismissal reasons into an explicit Other group; Other never qualifies a guideline gap by itself.
- Added a reviewer-decision coverage summary and per-rule evidence table so low sample sizes are not presented as missing guidelines.
- Added tests for tenant scoping, completed-review filtering, verified actor propagation to service-only accept/reject RPCs, stale acceptance conflicts, Other-group behavior, and human rejection flow.

### Verification

- Focused backend analytics/API suite: **18 passed**.
- Focused frontend GuidelineGapPanel suite: **5 passed**.
- Full branch regression is pending after the final changes.
- No hosted database migration or deployment was performed.

## 2026-11-12 â€” Frontend redesign and whole-project integration hardening

### Scope
Worked only on `feat/frontend-redesign`, based on `main` commit `705c613`. No deployment, migration execution, production configuration change, merge, or change to the active staging revision test.

### Frontend
- Added the responsive editorial workspace shell, role-aware navigation, organization switcher, account footer, mobile drawer and secure-workspace header.
- Added a warm neutral / forest palette through Tailwind CSS 4 theme tokens; restored the original primary color tokens after the initial redesign stylesheet had omitted them.
- Kept system font stacks; no external font CDN or new package was introduced.
- Added route-level lazy loading with an in-shell loading fallback, page-entry motion, hover/press transitions and reduced-motion support.
- Added an application render error boundary with an honest recovery message.
- Removed nested dashboard links that triggered React hydration warnings.
- Removed import-time Supabase client creation from the data and auth modules. Authentication errors are caught and surfaced instead of escaping from the React effect.
- Review, image-upload and kit-lint requests now retain request correlation IDs in structured errors.

### Backend and integration
- Normalized FastAPI HTTP and request-validation errors into the documented `ErrorResponse` shape. Validation responses do not echo rejected input values.
- Validated inbound `X-Request-Id` values and ensured generic server/database errors return the request ID in both body and header.
- Removed exception-trace logging from review/upload failure paths; logs retain IDs, duration and error type, not exception content.
- Fixed `run_visual_analysis()` to forward the preview-approved provider request override and expected asset checksums to `VisualAnalyzer.analyze_assets()`.
- Added regression tests for preview context propagation, API error normalization, request-ID validation, exception-log redaction, lazy Supabase initialization, auth failure handling and the app error boundary.

### Verification
- `web: npm run build`: passed (Vite 8.3.5; production chunks emitted).
- `web: npm test`: **201 passed across 13 test files**.
- `engine: Python 3.12 -m compileall -q app`: passed.
- `engine: Python 3.12 -m pytest -q tests`: **733 passed, 4 skipped**.
- `git diff --check`: passed.
- One existing third-party warning remains: Starlette's deprecation notice for using `httpx` with `TestClient` in `test_cors_origins.py`. No tests failed.

### Not verified / remaining work
- The branch has not been deployed, so the redesign has not been visually inspected in a real browser against the live staging API.
- No live Supabase migration or database mutation was run. SQL migration review was static: 18 created tables had matching RLS enablement statements; security-definer functions had fixed empty search paths in the reviewed migrations.
- `ARCHITECTURE.md` and `docs/AGENTS.md` still describe the original Round 2 build window and say visual review/redaction are out of scope. Those documents are historical and now conflict with the codebase; they were not rewritten without the architect's separate approval.
- Existing API and data workflows remain the source of truth; this branch does not introduce new product phases or change review/approval state transitions.

### Explainability
1. The browser remains a UI and direct-RLS reader; the FastAPI engine remains the trusted review service.
2. Workflow state changes remain database-function controlled; no service key moved to the browser.
3. The new visual shell changes presentation and loading behaviour, not review data contracts.
4. Error envelopes carry a stable request ID so the UI can show a support reference without exposing internal exception details.
5. The visual analyzer now receives the same approved provider request and asset checksums captured by the preview flow.
