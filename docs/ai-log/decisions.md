# Decisions Log

All deviations from specification and architectural decisions recorded here.

## Format

| Date | Decision | Reason | Approved By | Deviates? |
|------|----------|--------|-------------|-----------|

---

## 2026-11-04 | Slice 0: Repository Structure & Hello-World

| Date | Decision | Reason | Approved By | Deviates? |
|------|----------|--------|-------------|-----------|
| 2026-11-04 | Used `pydantic-settings` for config instead of plain `pydantic` | Required for `BaseSettings` in Pydantic V2 | Siddhartha | No (implementation detail) |
| 2026-11-04 | Added `vitest` to web devDependencies | Testing framework for future slices; no tests written in Slice 0 | Siddhartha | No (allowed stack includes Vitest) |
| 2026-11-04 | Used `@tailwindcss/vite` plugin for Tailwind CSS 4 integration | Official recommended approach for Vite + Tailwind 4 | Siddhartha | No (implementation detail) |
| 2026-11-04 | Engine health endpoint at `/v1/health` (not `/health`) | Matches API_CONTRACT.md §5.4 | Siddhartha | No (spec-compliant) |
| 2026-11-04 | CORS `allow_methods` limited to GET, POST, OPTIONS | Security: only methods needed for current and planned endpoints | Siddhartha | No (spec says CORS from ALLOWED_ORIGINS, no wildcard) |
| 2026-11-04 | Web app proxies `/v1` to engine in dev via Vite proxy | Avoids CORS issues during development | Siddhartha | No (dev-only convenience) |
| 2026-11-04 | Health check component sends `X-Request-Id` header | Demonstrates middleware working end-to-end | Siddhartha | No (spec requires X-Request-Id middleware) |

---

## Future Decisions

*To be added as slices progress.*

## 2026-11-12 | Frontend and reliability hardening (approved isolated branch)

| Date | Decision | Reason | Approved By | Deviates? |
|------|----------|--------|-------------|-----------|
| 2026-11-12 | Keep the existing Vite + React architecture; do not migrate to Next.js for the redesign | AnchorDraft is an authenticated client application; the requested visual and interaction improvements do not require SSR or a framework migration | Siddhartha (explicit request) | No |
| 2026-11-12 | Extend the isolated `feat/frontend-redesign` branch to include integration, error-handling, accessibility and performance fixes in existing flows | The architect explicitly requested a whole-project review and hardening pass; production and the revision-test staging environment remain untouched | Siddhartha (explicit request) | Yes — approved scope extension |
| 2026-11-12 | Use system font stacks and existing Tailwind 4 tokens; add no external font service or new dependency | Preserve the allowed stack and avoid introducing a runtime CDN dependency | Siddhartha (explicit request) | No |
| 2026-11-12 | Normalize framework HTTP and request-validation errors to the documented API error envelope; validate request IDs and keep exception details out of logs | Align implementation with API_CONTRACT.md and the repository's privacy/logging requirements | Siddhartha (explicit request) | No |
| 2026-11-12 | Forward the preview-approved vision request and expected asset checksums through the visual-analysis wrapper | The wrapper accepted these security/integrity inputs but failed to pass them to the analyzer | Siddhartha (explicit request) | No |
