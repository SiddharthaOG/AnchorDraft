# AI Log

## 2026-11-04 — Slice 0: Repository Skeleton & Hello-World Pipeline

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
3. Implement monorepo layout per ARCHITECTURE.md §5.1
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
5. **Single commit** - All Slice 0 work in one commit; future slices should use smaller, reviewable commits per AGENTS.md §4

---

## 2026-11-05 — Slice 0: Corrections & Verification

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
# → 14 passed (9 original + 5 new comma-separated tests)

# Web
cd web
npm ci
npm run test
# → 7 passed
npm run build
# → success (223 KB JS, 9 KB CSS gzipped)

# Engine health endpoint verification
uvicorn app.main:app --port 8000
curl http://localhost:8000/v1/health
# → {"status":"ok","version":"0.1.0","time":"..."}
```

### Test/Build Results

| Check | Result |
|-------|--------|
| Engine install (`pip install -e ".[test]"`) | ✅ Success |
| Engine tests (`pytest`) | ✅ 14 passed |
| Web install (`npm ci`) | ✅ Success |
| Web tests (`npm run test`) | ✅ 7 passed |
| Web build (`npm run build`) | ✅ Success (223 KB JS, 9 KB CSS) |
| Engine health endpoint | ✅ Returns `{status, version, time}` |
| CORS preflight (JSON array origins) | ✅ 200 with correct headers |
| CORS preflight (comma-separated origins) | ✅ 200 with correct headers |
| X-Request-Id middleware | ✅ Generated/echoed correctly |
| No secrets in tracked files | ✅ Verified |

### Deployment Status

| Target | Status | Notes |
|--------|--------|-------|
| Vercel (Web) | Not deployed | Requires Vercel project creation and env vars |
| Render (Engine) | Not deployed | Requires Render service creation and env vars |
| Supabase | Not created | Requires Supabase project creation |

### Remaining Blockers

1. **Architecture decision status conflict** — Needs architect to confirm which decisions are actually DECIDED vs PROPOSED.
2. **No CI pipeline** — Recommended but not required for Slice 0.
3. **External service credentials** — Vercel, Render, Supabase require human setup; no secrets in repo.

### Recommended Next Action

1. Architect reviews and resolves decision status in ARCHITECTURE.md.
2. Human creates Vercel/Render/Supabase projects and configures env vars.
3. Proceed to Slice 1 (Schema, auth, roles, RLS) after approval.


## 2026-11-12 — Improvement 2 Integration Hardening Follow-up

### Summary

Traced the reported Start Review no-response regression against the deployed staging service. Render request logs showed that the browser had reached `POST /v1/reviews/preview`, which returned HTTP 422. The previous frontend error parser did not understand FastAPI's array-shaped validation details, and the error was only placed in the page-level toast. The UI now renders preview failures directly beside the Start Review control and translates FastAPI validation details into a readable message.

### Changes

- Updated `web/src/lib/data.ts` to extract FastAPI request-validation locations and messages from `detail[]`, preserving a machine-readable `request_validation_error` reason.
- Updated `ContentDetail` to show preview failures inline in the Review Status panel; the button retains immediate pending feedback and is disabled while the request is in flight.
- Added frontend tests for FastAPI 422 parsing and inline preview failure visibility.
- Configured the **staging Render service only** to select Gemini as its primary provider (`LLM_PROVIDER=gemini`, model `gemini-3.8-flash`). Disabled provider fallback because only the Gemini credential was confirmed for this staging configuration; no second provider credential was assumed. No secret values were read or written to the repository.

### Verification

- Engine: `py -3.12 -m pytest tests -q` — **702 passed, 4 skipped, 2 warnings**.
- Web: `npm test -- --reporter=dot` — **183 passed**.
- Web: `npm run build` — succeeded; existing Vite dynamic-import warning remains.
- Provider factory smoke test with a non-secret placeholder credential and staging environment — instantiated `GeminiProvider` with model `gemini-3.8-flash`; this verifies provider selection, not the real API credential.
- Render staging `/v1/health?deep=1` — `status=ok`, database connected.
- Render CORS preflight for the current Vercel branch alias — HTTP 200 with the exact allow-origin and required headers.
- Vercel branch deployment for commit `d6fb3e1` — READY and assigned to the branch alias.

### Not Yet Verified

- The exact cause inside the earlier HTTP 422 response was not retained in Render logs. The frontend now exposes FastAPI's validation details on the next request; an authenticated browser retest is still required to capture and resolve any underlying request-shape issue.
- No authenticated preview → consent → confirmation → Gemini provider call was executed in this pass. Real provider acceptance, returned findings, and audit rows remain end-to-end checks, not claimed as complete.
- Visual asset upload → vision analysis → visual findings and UI rendering remain end-to-end checks. Automated visual and confidentiality suites pass, but this does not replace a live workflow test.
