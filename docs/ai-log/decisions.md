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