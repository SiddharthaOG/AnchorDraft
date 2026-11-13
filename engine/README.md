# AnchorDraft Engine

Python/FastAPI service responsible for authenticated API operations, organisation and role enforcement, review orchestration, deterministic checks, AI-provider integration, and backend validation.

## Prerequisites

- Python 3.11 or newer (deployment currently uses Python 3.12.10)
- [uv](https://docs.astral.sh/uv/) recommended, or pip
- A running PostgreSQL database
- A Supabase project (local or hosted)
- Provider credentials for a real LLM provider outside local/test environments

## Quick start

From the repository root:

```bash
cd engine
cp .env.example .env
```

Fill in the required values in `.env`. For local development with the Supabase CLI, start the stack from the repository root first:

```bash
cd ..
supabase start
supabase status
supabase db reset
cd engine
```

Use the connection string, API URL, anon key, and service-role key reported by `supabase status`. The local database default is normally:

```text
postgresql://postgres:postgres@127.0.0.1:55432/postgres
```

Install dependencies and run the service:

```bash
uv sync --extra test
uv run uvicorn app.main:app --reload
```

Health endpoint: `http://127.0.0.1:8000/v1/health`.

### pip alternative

```bash
python -m venv .venv
# Activate .venv, then:
pip install -e ".[test]"
uvicorn app.main:app --reload
```

## Required configuration

See [.env.example](.env.example). The following settings are required for a working authenticated service:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | Explicit runtime environment: `development`, `test`, `staging`, or `production` (aliases are also accepted) |
| `DATABASE_URL` | PostgreSQL connection string used by the asyncpg pool |
| `SUPABASE_URL` | Supabase API URL used by the service-role client |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only key used for privileged Supabase data access |
| `SUPABASE_JWKS_URL` | Supabase project's JWT signing-key JWKS endpoint |
| `SUPABASE_ISSUER` | Expected JWT issuer, normally `<SUPABASE_URL>/auth/v1` |
| `SUPABASE_AUDIENCE` | Expected JWT audience; normally `authenticated` |
| `ALLOWED_ORIGINS` | Explicit browser origins allowed by CORS |

For a local Supabase stack, the typical URL values are:

```dotenv
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_JWKS_URL=http://127.0.0.1:54321/auth/v1/.well-known/jwks.json
SUPABASE_ISSUER=http://127.0.0.1:54321/auth/v1
SUPABASE_AUDIENCE=authenticated
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres
```

For hosted Supabase, use the project URL and the matching hosted Auth JWKS and issuer URLs. Do not copy local URLs into Render.

## LLM provider configuration

Supported provider values are:

- `fake`: deterministic/local testing only. The application rejects this provider in staging and production.
- `groq`: real Groq provider.
- `gemini`: real Google Gemini provider.

Primary and fallback providers are configured independently:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Primary provider: `fake`, `groq`, or `gemini` |
| `LLM_FALLBACK_PROVIDER` | Fallback provider |
| `LLM_FALLBACK_ENABLED` | Enables/disables fallback |
| `GROQ_API_KEY` | Groq credential |
| `GROQ_MODEL` | Groq text model identifier |
| `GROQ_VISION_MODEL` | Groq vision model identifier |
| `GROQ_TPM_LIMIT`, `GROQ_RPM_LIMIT` | Configured Groq rate limits |
| `GEMINI_API_KEY` | Gemini credential |
| `GEMINI_MODEL` | Primary Gemini model identifier |
| `GEMINI_FALLBACK_MODEL` | Distinct Gemini model used for same-provider fallback |
| `GEMINI_TPM_LIMIT`, `GEMINI_RPM_LIMIT` | Configured Gemini rate limits |

A non-local deployment must have credentials for every enabled provider that may be used. Do not set `LLM_PROVIDER=fake` on Render. Model availability and quotas depend on the provider account; configure values that are available to your project.

## Confidentiality preview encryption

The short-lived review-preview flow uses `PREVIEW_ENCRYPTION_KEY` to encrypt the placeholder reverse map.

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the generated value in the engine environment only. Never commit it. Every running engine instance sharing preview records must use the same key. A key mismatch makes pending previews undecryptable; rotate only after pending previews have expired or been consumed.

The preview flow stores redacted provider prompts and a payload hash. The placeholder reverse map is encrypted and cleared after terminal processing. Preview records expire after 10 minutes. If attached images are sent to a vision provider, the creator must explicitly consent; image bytes are not OCR-redacted.

Apply the relevant Supabase migration before enabling the preview endpoints. Keep local and hosted migration histories aligned using the Supabase CLI; do not manually replay already-applied production migrations.

## API surface

All routes are versioned under `/v1`. The service includes:

- Health checks.
- Review creation and confidentiality preview/confirmation flows.
- Text/PDF/DOCX import.
- Brand Kit linting and draft-kit operations.
- Guideline-gap analytics and suggestion operations.
- Organisation confidentiality-policy operations.

The live OpenAPI schema is available from the running FastAPI application at `/docs` (unless disabled by deployment configuration). The API contract document describes the broader application data-access surfaces, including Supabase RPC and RLS-backed browser operations.

## Tests

From `engine/`:

```bash
uv run pytest -v
```

Or with an activated pip environment:

```bash
python -m pytest tests/ -v
```

## CORS

`ALLOWED_ORIGINS` accepts either a JSON array or a comma-separated list. Example:

```dotenv
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

The service also permits the project's configured Vercel preview hostname pattern. Wildcard origins are not used. Keep production origins limited to the actual frontend domains.

## Deployment on Render

- Repository: `SiddharthaOG/AnchorDraft`
- Root directory: `engine/`
- Python version: `PYTHON_VERSION=3.12.10`
- Build command: `pip install -e .`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Set all required environment variables in the Render dashboard. In particular, configure `ENVIRONMENT=production` (or `staging`), `DATABASE_URL`, Supabase URL/service-role/JWKS/issuer/audience values, exact `ALLOWED_ORIGINS`, a real primary LLM provider and credentials, and the fallback provider credentials if fallback is enabled. Configure `PREVIEW_ENCRYPTION_KEY` for confidentiality preview processing.

Never put server-side credentials in the frontend's `VITE_*` environment variables.
