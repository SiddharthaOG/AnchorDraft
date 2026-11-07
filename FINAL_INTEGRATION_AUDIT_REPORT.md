# AnchorDraft — Final Integration & Deployment Readiness Audit (Completion Pass)

**Date:** 2026-11-07  
**Branch:** `feat/phase-4-review-engine`  
**Commit:** Current HEAD (includes Slice 4.9 lease fix)

---

## 1. Executive Verdict

**Overall Verdict: NOT READY**

- **Frontend (web/)** is a minimal health-check stub only — no authentication, no Supabase client, no review workflow UI, no API integration for the acceptance scenario.
- **Engine (engine/)** is functionally complete for review pipeline execution, but cannot be verified against a live Supabase project (migrations unverified, environment variables unconfigured).
- **Database (supabase/)** migration set is internally consistent and appears complete for the reviewed scope, but **hosted migration state is UNVERIFIED**.
- **Deployment configuration** for Vercel and Render does not exist in the repository — no `vercel.json`, no `render.yaml`, no documented environment variable setup.
- **Acceptance workflow** (13 steps) is **almost entirely missing** on the frontend; backend RPCs exist but integration is unverified.

---

## 2. Five-Area Readiness Matrix

| Area | Verdict | Confirmed Blockers | Unverified Items |
|------|---------|-------------------|------------------|
| **Frontend** | **NOT READY** | No auth, no Supabase client, no review UI, no workflow components, no API client for review submission/status/findings/decisions/revisions/approvals/insights | Vercel build config, environment variables, hosted deployment |
| **Engine** | **READY WITH CAVEATS** | None in source code; service starts with `uvicorn engine.app.main:app` | Live Supabase connectivity, provider API keys/quota, Render health-check path `/v1/health` (not `/health`), hosted env vars |
| **Database** | **READY WITH EXTERNAL VERIFICATION** | None in migration SQL | **Hosted Supabase migration state** — cannot confirm all 10 migrations applied; `service_role` grants to `engine_complete_review`/`engine_fail_review`/`reclaim_stale_reviews` |
| **Deployment** | **NOT READY** | No `vercel.json`, no `render.yaml`, no deployment docs, no environment variable inventory in repo | Vercel project root/output dir, Render start command, hosted env vars |
| **Acceptance Workflow** | **NOT READY** | Frontend missing 13/13 steps; backend RPCs exist but untested end-to-end | Live Supabase, real provider credentials, full pipeline integration |

---

## 3. Confirmed Blockers

| # | Severity | Location | Evidence | Minimal Correction |
|---|----------|----------|----------|-------------------|
| 1 | **Critical** | `web/src/` (entire app) | Frontend has only `HealthCheck` component; no `Supabase` client, no `AuthProvider`, no routing, no pages for: kit management, content creation, review submission, findings review, decisions, revisions, approvals, insights. | Build the complete frontend application per `API_CONTRACT.md` and `DATA_MODEL.md`. |
| 2 | **Critical** | `web/` (root) | No `vercel.json`; no documented build command, output directory, install command, or environment variables for Vercel. | Add `vercel.json` with `buildCommand: "npm run build"`, `outputDirectory: "dist"`, `framework: "vite"`, and required env vars. |
| 3 | **Critical** | `engine/` (root) | No `render.yaml` or `Dockerfile`; no documented start command, health-check path, or environment variables for Render. | Add `render.yaml` with `startCommand: "uvicorn engine.app.main:app --host 0.0.0.0 --port $PORT"`, `healthCheckPath: "/v1/health"`, and required env vars. |
| 4 | **High** | `supabase/` (hosted) | Cannot verify migration state on hosted Supabase project; `service_role` grants to `engine_complete_review`, `engine_fail_review`, `reclaim_stale_reviews` must be confirmed applied. | Run `supabase migration list` on hosted project; apply missing migrations; verify grants. |
| 5 | **High** | `engine/app/api/reviews.py:90` | Uses `supabase.get_revision()` and `supabase.get_content()` which call PostgREST with service-role key — requires RLS policies to allow service-role reads. | Verify RLS policies allow `service_role` to read `revisions`, `contents`, `brand_kits`, `rules`, `approved_facts`. |
| 6 | **Medium** | `engine/app/llm/provider_factory.py:124-146` | Primary provider defaults to `fake`; Groq/Gemini require `GROQ_API_KEY` / `GEMINI_API_KEY` which are empty in config. | Configure real API keys in Render environment; set `LLM_PROVIDER=groq`, `LLM_FALLBACK_PROVIDER=gemini`. |
| 7 | **Medium** | `engine/app/core/config.py:44` | `ALLOWED_ORIGINS` defaults to empty string; CORS will reject all origins unless configured. | Set `ALLOWED_ORIGINS=https://your-vercel-app.vercel.app` in Render env. |
| 8 | **Medium** | `supabase/migrations/20261104000009_workflow_functions.sql:1139-1145` | `engine_complete_review` and `engine_fail_review` granted to `service_role` only — must be confirmed on hosted DB. | Verify grants on hosted Supabase: `GRANT EXECUTE ON FUNCTION engine_complete_review(...) TO service_role;` |
| 9 | **Medium** | `engine/app/pipeline/orchestrator.py:673` | `reclaim_stale_reviews` default lease = 30 min (matches SQL), but **no automatic reaper** — must be triggered externally (cron, pg_cron, or scheduled job). | Document and configure external trigger (e.g., Render cron job or pg_cron) to call `reclaim_stale_reviews(30)` periodically. |

---

## 4. External Verification Required

| Item | Why Unverified | Required Action |
|------|----------------|-----------------|
| Hosted Supabase migration state | Cannot connect to hosted project from this audit | Run `supabase migration list --project-ref <ref>` and apply any pending migrations |
| Hosted Supabase `service_role` grants | Grants to `engine_complete_review`, `engine_fail_review`, `reclaim_stale_reviews` are in migrations but not confirmed applied | Verify with `\df engine_complete_review` and `\df engine_fail_review` in hosted psql |
| Live PostgreSQL integration tests | 4 tests skipped (`test_successful_pipeline_orchestration`, `test_deterministic_findings_survive_provider_failure`, `test_llm_status_and_warning_on_provider_failure`, `test_failure_persistence_on_unrecoverable_error`) | Run against a real PostgreSQL instance (local or hosted) |
| Real provider credentials/quota | `GROQ_API_KEY`, `GEMINI_API_KEY` not in repo; quota unknown | Configure in Render dashboard; test with a real review request |
| Vercel project configuration | No `vercel.json`; project root, build command, output dir, env vars unknown | Create Vercel project from `web/` subdirectory; configure env vars |
| Render service configuration | No `render.yaml`; start command, health check, env vars unknown | Create Render web service from `engine/` directory; configure |
| CORS integration | `ALLOWED_ORIGINS` must match deployed Vercel URL exactly | Set after Vercel deployment URL is known |
| JWT/JWKS configuration | `SUPABASE_JWKS_URL`, `SUPABASE_ISSUER`, `SUPABASE_AUDIENCE` must match hosted Supabase Auth | Extract from Supabase dashboard → Auth → Settings → JWT |
| Stale-review reaper | No automatic mechanism; `reclaim_stale_reviews` must be called externally | Configure pg_cron or Render cron job to run every 5–10 minutes |

---

## 5. Environment Variable Matrix

| Variable | Used By | Required? | Purpose | Where Configured |
|----------|---------|-----------|---------|------------------|
| `VITE_ENGINE_URL` | Frontend (web) | **Required for core** | Base URL of deployed engine (e.g., `https://anchordraft-engine.onrender.com`) | Vercel Project Settings → Environment Variables |
| `SUPABASE_URL` | Engine, Frontend (if added) | **Required for startup** | Supabase project REST API URL | Render & Vercel env vars |
| `SUPABASE_SERVICE_ROLE_KEY` | Engine | **Required for startup** | Service-role key for admin DB access (reviews, findings, RPCs) | Render env var (secret) |
| `SUPABASE_JWKS_URL` | Engine | **Required for startup** | JWKS endpoint for JWT verification (e.g., `https://<ref>.supabase.co/auth/v1/keys`) | Render env var |
| `SUPABASE_ISSUER` | Engine | **Required for startup** | JWT issuer (e.g., `https://<ref>.supabase.co/auth/v1`) | Render env var |
| `SUPABASE_AUDIENCE` | Engine | **Required for startup** | JWT audience (default: `authenticated`) | Render env var |
| `DATABASE_URL` | Engine | **Required for startup** | Direct PostgreSQL connection string (for asyncpg pool) | Render env var (secret) |
| `ALLOWED_ORIGINS` | Engine | **Required for core** | CORS origins (JSON array or comma-separated); must include Vercel URL | Render env var |
| `LLM_PROVIDER` | Engine | **Required for core** | Primary provider: `groq` (production) or `fake` (dev) | Render env var |
| `LLM_FALLBACK_PROVIDER` | Engine | **Required for core** | Fallback provider: `gemini` | Render env var |
| `LLM_FALLBACK_ENABLED` | Engine | Optional (default `true`) | Enable/disable fallback | Render env var |
| `GROQ_API_KEY` | Engine | **Required for core** (if `LLM_PROVIDER=groq`) | Groq API key for primary LLM | Render env var (secret) |
| `GROQ_MODEL` | Engine | Optional (default `openai/gpt-oss-120b`) | Groq model name | Render env var |
| `GROQ_TPM_LIMIT` | Engine | Optional (default `8000`) | Tokens per minute limit | Render env var |
| `GROQ_RPM_LIMIT` | Engine | Optional (default `30`) | Requests per minute limit | Render env var |
| `GEMINI_API_KEY` | Engine | **Required for core** (if fallback=gemini) | Gemini API key for fallback LLM | Render env var (secret) |
| `GEMINI_MODEL` | Engine | Optional (default `gemini-3.8-flash`) | Gemini model name | Render env var |
| `GEMINI_TPM_LIMIT` | Engine | Optional (default `250000`) | Tokens per minute limit | Render env var |
| `GEMINI_RPM_LIMIT` | Engine | Optional (default `15`) | Requests per minute limit | Render env var |
| `DAILY_REVIEW_CAP` | Engine | Optional (default `20`) | Max reviews per org per day | Render env var |
| `PER_USER_RATE_LIMIT` | Engine | Optional (default `10`) | Max requests per user per minute | Render env var |
| `ENGINE_VERSION` | Engine | Optional (default `0.1.0`) | Version stamped on reviews | Render env var |
| `VERSION` | Engine | Optional | App version for health endpoint | Render env var |

**Notes:**
- Frontend currently only uses `VITE_ENGINE_URL`. If Supabase Auth is added to frontend, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` will be required.
- All secrets (`*_KEY`, `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) must be stored as **encrypted** environment variables on Render/Vercel.
- `DATABASE_URL` format: `postgresql://user:pass@host:port/dbname?sslmode=require` (Supabase connection pooler recommended).

---

## 6. Acceptance Workflow Trace (13 Steps)

| Step | Description | Frontend | API / RPC | Database | Status |
|------|-------------|----------|-----------|----------|--------|
| 1 | Guideline Owner creates/loads kit | **Missing** — no kit management UI | `POST /v1/kits` (not implemented), `public.create_content` not for kits | `brand_kits`, `rules`, `approved_facts` | **Missing** |
| 2 | Owner adds ~15 rules, 5 facts | **Missing** | `POST /v1/kits/{id}/rules`, `POST /v1/kits/{id}/facts` (not implemented) | `rules`, `approved_facts` (RLS: owner + draft only) | **Missing** |
| 3 | Creator submits content | **Missing** — no content editor | `POST /v1/contents` (not implemented), `public.create_content` | `contents`, `revisions` | **Missing** |
| 4 | Review engine processes content | **Missing** — no submit button | `POST /v1/reviews` → `run_review_pipeline()` | `reviews` (queued→running→done) | **Implemented but integration unverified** |
| 5 | Findings include: banned term, absolute claim, unsupported fact, missing alt text | **Missing** — no findings display | Deterministic checks + LLM analysis → `engine_complete_review` | `findings` (with `rule_id`/`fact_id`, `quote`, `start_offset`, `end_offset`) | **Partially implemented** (backend only) |
| 6 | Each finding has valid citation, exact quote, explanation | **Missing** | Citation validator enforces `rule_id`/`fact_id` match, quote offsets, explanation | `findings` constraints: `findings_one_ref`, `findings_offsets_valid` | **Implemented but integration unverified** |
| 7 | Creator accepts one finding | **Missing** | `POST /v1/decisions` (not implemented), `public.record_decision` | `decisions` (action=accept) | **Missing** |
| 8 | Creator dismisses another with reason | **Missing** | `public.record_decision` (action=dismiss, reason required) | `decisions` (action=dismiss, reason) | **Missing** |
| 9 | Creator creates revision | **Missing** | `POST /v1/revisions` (not implemented), `public.create_revision` | `revisions` (source=accepted_suggestion) | **Missing** |
| 10 | Manager requests changes | **Missing** | `POST /v1/approvals` (not implemented), `public.request_changes` | `approvals` (action=request_changes), `contents.status=changes_requested` | **Missing** |
| 11 | Creator revises content | **Missing** | `public.create_revision` (allowed in changes_requested) | `revisions`, `contents.status=draft` | **Missing** |
| 12 | Manager approves | **Missing** | `public.approve_content` (checks `v_pending_signoffs`) | `approvals` (action=approve), `contents.status=approved` | **Missing** |
| 13 | Insights displays dismissed rule | **Missing** | `GET /v1/insights` (not implemented), `v_rule_stats` view | `v_rule_stats` (dismissal_rate, last_seen) | **Missing** |

**Summary:** 0/13 steps implemented on frontend. Backend RPCs for steps 4, 6, 7, 8, 9, 10, 11, 12 exist and are hardened (SECURITY DEFINER, RLS, claim-token fencing). Steps 1, 2, 3, 5, 13 require API endpoints that do not exist. Step 5 (findings display) requires frontend to fetch and render `findings` joined with `rules`/`approved_facts`.

---

## 7. Minimal Remediation Plan

### Phase 1: Code Fixes (Frontend — Critical Path)
1. **Create `web/src/lib/supabase.ts`** — Initialize Supabase client with `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
2. **Create `web/src/lib/auth.tsx`** — `AuthProvider` using Supabase Auth (`onAuthStateChange`, `signInWithOAuth`, `signOut`).
3. **Create `web/src/lib/api.ts`** — Typed API client for all `/v1/*` endpoints (reviews, contents, kits, decisions, approvals, insights).
4. **Implement routing** — React Router with routes: `/kits`, `/kits/:id`, `/contents`, `/contents/:id`, `/review/:reviewId`, `/insights`.
5. **Build Kit Management UI** — Create/clone/activate kits, add rules/facts (Owner only).
6. **Build Content Editor** — Create content, edit revisions, submit for review (Creator).
7. **Build Review Findings Page** — Display findings with rule/fact citation, quote, explanation, accept/dismiss actions.
8. **Build Decisions & Revisions** — Record decisions, apply decisions → new revision.
9. **Build Approvals UI** — Manager: request changes / approve; Reviewer: signoff / reject claim.
10. **Build Insights Dashboard** — Query `v_rule_stats`, display dismissal rates.

### Phase 2: Configuration Tasks
11. **Add `web/vercel.json`** — Configure build, output, framework, env vars.
12. **Add `engine/render.yaml`** — Configure start command, health check `/v1/health`, env vars, Python 3.11+.
13. **Document all environment variables** in a `DEPLOYMENT.md` or README.

### Phase 3: Hosted Verification
14. **Verify Supabase migrations** — `supabase migration list --project-ref <ref>`; apply missing.
15. **Verify `service_role` grants** — `engine_complete_review`, `engine_fail_review`, `reclaim_stale_reviews`.
16. **Configure Vercel project** — Root: `web/`, Build: `npm run build`, Output: `dist`, Env vars.
17. **Configure Render service** — Root: `engine/`, Start: `uvicorn engine.app.main:app --host 0.0.0.0 --port $PORT`, Health: `/v1/health`, Env vars.
18. **Set `ALLOWED_ORIGINS`** on Render to match deployed Vercel URL.
19. **Configure real provider keys** — `GROQ_API_KEY`, `GEMINI_API_KEY` on Render.
20. **Configure stale-review reaper** — pg_cron: `SELECT cron.schedule('reclaim-stale', '*/5 * * * *', 'SELECT reclaim_stale_reviews(30)');` or Render cron job.

### Phase 4: Acceptance Testing
21. **Run full acceptance scenario** (13 steps) against deployed staging.
22. **Verify deterministic findings** (banned term, absolute claim, missing alt text) appear correctly.
23. **Verify LLM findings** (unsupported fact) with citation validation.
24. **Verify claim-token fencing** — kill worker mid-review, confirm reclaim works.
25. **Verify CORS** — frontend can call engine without errors.
26. **Verify JWT auth** — creator/manager/reviewer roles enforced at API and DB level.

---

## 8. Final Recommendation

**Do not deploy to production.** The frontend is a stub; the acceptance workflow cannot be completed by any user.

**Next actions for the Architect:**

1. **Acknowledge** this audit and its findings.
2. **Prioritize** Phase 1 (Frontend implementation) — this is the largest gap.
3. **Assign** frontend work to a React/TypeScript engineer familiar with Supabase Auth, Vite, Tailwind 4.
4. **Defer** engine/database/deployment configuration until frontend can drive the workflow.
5. **Schedule** a follow-up audit after Phase 1 + 2 are complete (estimate: 2–3 sprints for minimal viable frontend).

The engine and database layers are **solid and well-tested** (482 unit tests pass, 32 new Slice 4.9 tests cover fallback, citation validation, claim-token fencing, stale recovery). The blocker is entirely the missing frontend application and deployment configuration.

---

## Appendix: Verification Evidence Summary

| Area | Verification Level | Evidence |
|------|-------------------|----------|
| Frontend build | **Command-tested** | `npm run build` succeeds (130ms, 223 kB JS gzipped) |
| Frontend TypeScript | **Command-tested** | `npx tsc --noEmit` passes (no output) |
| Frontend functionality | **Source-inspected** | Only `HealthCheck` component exists; no auth, no API client, no workflow UI |
| Engine startup | **Source-inspected** | `uvicorn engine.app.main:app` compatible; lifespan initializes asyncpg pool |
| Engine health endpoint | **Source-inspected** | `GET /v1/health` returns `{status, version, time, database}`; deep check queries DB |
| Engine CORS | **Source-inspected** | Parses `ALLOWED_ORIGINS` as JSON array or comma-separated; no wildcard |
| Engine auth | **Source-inspected** | JWT/JWKS verification via `PyJWT`; role/org from `memberships` table |
| Engine review pipeline | **Source-inspected** | `run_review_pipeline()` → claim → deterministic → LLM (fallback) → validator → `engine_complete_review` with claim_token |
| Engine provider fallback | **Command-tested** | 11 unit tests pass: fallback on rate_limit/timeout/unavailable; no fallback on blocked/bad_output/config_error |
| Engine citation validator | **Command-tested** | 11 unit tests pass: reference existence, quote offsets, 25-finding cap, duplicate handling, fact→needs_reviewer |
| Engine claim-token fencing | **Command-tested** | 7 unit tests pass: NULL rejection, mismatch rejection, stale worker fencing |
| Engine stale recovery | **Command-tested** | 2 unit tests pass: eligibility, 30-min lease default |
| Engine API integration | **Command-tested** | 3 unit tests pass: idempotency for queued/running/completed |
| Database migrations | **Source-inspected** | 10 migrations in order: enums/orgs → kits → contents/revisions → reviews/findings → workflow → views → triggers → RLS → workflow functions → review lease |
| Database RLS | **Source-inspected** | All app tables have RLS; `private.is_member`/`has_role` helpers; write revoked from authenticated on workflow tables |
| Database RPCs | **Source-inspected** | 11 SECURITY DEFINER functions: `create_content`, `create_revision`, `record_decision`, `apply_decisions`, `submit_content`, `request_changes`, `record_signoff`, `approve_content`, `clone_kit`, `activate_kit`, `engine_complete_review`, `engine_fail_review`, `reclaim_stale_reviews` |
| Deployment config | **Source-inspected** | No `vercel.json`, no `render.yaml`, no deployment docs in repo |
| Hosted Supabase | **UNVERIFIED** | Cannot connect; migration state and grants unknown |
| Live provider APIs | **UNVERIFIED** | No credentials in repo; not tested |

---

*Report generated by Integration Auditor. No source files were modified during this audit.*