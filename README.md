<div align="center">

# ⚓ AnchorDraft

**Pre-publication brand-governance and content-compliance platform.**

Review content against organisation-specific brand rules, manage findings across revisions, and move submissions through human-led review and approval.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-20232A?style=flat-square&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite)](https://vite.dev/)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres%20%2B%20Auth-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com/)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=flat-square&logo=python)](https://python.org/)

[Live application](https://anchordraft.vercel.app/) · [API health](https://anchordraft.onrender.com/v1/health) · [Architecture](docs/ARCHITECTURE.md)

</div>

---

## What it does

AnchorDraft helps organisations apply their own brand, editorial, and content requirements before publication. It combines:

- **Brand Kits:** versioned, organisation-specific rules, approved facts, and visual guideline settings.
- **Deterministic linting:** repeatable checks against configured rules.
- **AI-assisted review:** candidate findings supported by rule/fact references and quoted draft text.
- **Revision-aware workflows:** findings and decisions are evaluated against the relevant content revision.
- **Human review and approvals:** Creator, Reviewer, Manager, and Owner workflows.
- **Confidentiality-aware processing:** sensitive-data redaction, outbound payload preview, and explicit confirmation before external AI processing.
- **Guideline-gap analytics:** recurring review outcomes can inform proposed guideline improvements, subject to human approval.
- **Auditability:** important administrative operations are recorded.

AI output is advisory. Authorised people retain responsibility for review and approval decisions. Visual compliance currently uses structured guideline configuration and deterministic checks; it is not pixel-perfect visual recognition or automated logo identity detection.

## Application and repository

| Resource | Location |
|---|---|
| Production frontend | https://anchordraft.vercel.app/ |
| Production API health | https://anchordraft.onrender.com/v1/health |
| Public source repository | https://github.com/SiddharthaOG/AnchorDraft |

The public URL loads the application shell. Protected workspaces require an authorised account. Demo credentials should be distributed separately to intended evaluators; do not commit passwords or production secrets to this repository.

## Architecture

| Layer | Technology | Responsibility |
|---|---|---|
| Web | React, TypeScript, Vite, Tailwind CSS | Application UI and authenticated user workflows |
| API | Python, FastAPI | Authentication, role/tenant checks, validation, review orchestration |
| Identity and data | Supabase Auth, PostgreSQL | User identity, organisation membership, application data and RLS |
| Review providers | Provider adapter for Groq/Gemini; fake provider for local tests | AI-assisted text and vision analysis |
| Hosting | Vercel, Render, Supabase | Frontend, API service, database and authentication |

The browser never receives the Supabase service-role key or an AI-provider key. The backend verifies Supabase access tokens and derives organisation membership and roles server-side.

## Repository layout

```text
AnchorDraft/
├── docs/                  # Architecture, data model, API and review-engine docs
├── engine/                # Python / FastAPI review service
│   ├── app/
│   ├── tests/
│   ├── .env.example
│   └── pyproject.toml
├── web/                   # React / TypeScript / Vite frontend
│   ├── src/
│   ├── .env.example
│   └── package.json
├── supabase/
│   ├── migrations/        # Ordered SQL migrations
│   ├── seed/              # Explicit local/demo seed scripts
│   └── config.toml
└── README.md
```

## Quick start

### Prerequisites

- Git
- Node.js **22.x** (the frontend declares Node 22.x)
- Python **3.11 or 3.12**; the deployed Render service is configured for Python 3.12.10
- [uv](https://docs.astral.sh/uv/) (recommended for Python dependency management)
- [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)
- Docker Desktop or another Docker-compatible runtime for the local Supabase stack

### 1. Clone the repository

```bash
git clone https://github.com/SiddharthaOG/AnchorDraft.git
cd AnchorDraft
```

### 2. Start the local Supabase stack

Docker must be running.

```bash
supabase start
supabase status
```

Keep the local API URL, database connection string, anon key, and service-role key from the status output. The local Supabase defaults used by this repository are documented in `supabase/config.toml`.

Apply the repository migrations to the local database:

```bash
supabase db reset
```

This resets **the local database only**, then replays the checked-in migrations. It does not create the demo Auth users automatically; see [Local database and demo seed setup](supabase/migrations/README.md).

### 3. Configure and run the backend

```bash
cd engine
```

Copy the environment template to `.env` and fill in the local Supabase values:

```bash
cp .env.example .env
```

At minimum, configure:
- `ENVIRONMENT=development`
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWKS_URL`
- `SUPABASE_ISSUER`
- `SUPABASE_AUDIENCE=authenticated`

For local Supabase, the usual URL forms are:
- API: `http://127.0.0.1:54321`
- JWKS: `http://127.0.0.1:54321/auth/v1/.well-known/jwks.json`
- Issuer: `http://127.0.0.1:54321/auth/v1`
- Database: `postgresql://postgres:postgres@127.0.0.1:55432/postgres`

Use the actual values reported by your local Supabase CLI if they differ. The local fake LLM provider is permitted only for local/test environments.

Install and run:

```bash
uv sync --frozen --extra test
uv run uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; health check: `http://127.0.0.1:8000/v1/health`.

**Alternative using pip:**

```bash
python -m venv .venv
# Activate the virtual environment, then:
pip install -e ".[test]"
uvicorn app.main:app --reload
```

### 4. Configure and run the frontend

In a second terminal:

```bash
cd web
cp .env.example .env
```

Set the local values for:
- `VITE_ENGINE_URL=http://127.0.0.1:8000`
- `VITE_SUPABASE_URL=http://127.0.0.1:54321`
- `VITE_SUPABASE_ANON_KEY` to the local anon key shown by `supabase status`

Install the exact frontend dependency versions from the committed npm lockfile and start Vite:

```bash
npm ci
npm run dev
```

Open `http://localhost:5173`.

> **Windows PowerShell:** `Copy-Item .env.example .env` can be used instead of `cp`. The remaining commands are the same when the required tools are on PATH.

## Local database and demo seed setup

The migration chain creates the schema and baseline organisation. Demo Auth users and sample application data are separate from schema migrations because their rows must reference real Auth user UUIDs.

Follow the exact sequence in [supabase/migrations/README.md](supabase/migrations/README.md):
1. Start local Supabase and run `supabase db reset`.
2. Create the local demo Auth users in Supabase Studio.
3. Run `supabase/seed/seed_users.sql` with their actual UUIDs.
4. Run `supabase/seed/seed_content.sql` with the Creator UUID.

The seed scripts are for local development/testing. They are not the production demo-account provisioning mechanism.

## Tests and builds

Backend (from `engine/`):

```bash
uv run pytest -v
```

Frontend (from `web/`):

```bash
npm test
npm run build
```

Database/schema tests and their prerequisites are documented in [supabase/migrations/README.md](supabase/migrations/README.md).

## Deployment

### Vercel — frontend

- Repository: `SiddharthaOG/AnchorDraft`
- Root directory: `web/`
- Node.js: 22.x (also declared in `web/package.json`)
- Install command: `npm ci`
- Build command: `npm run build`
- Output directory: `dist`

Set the variables from `web/.env.example`:
- `VITE_ENGINE_URL`: deployed Render API base URL, without a trailing slash
- `VITE_SUPABASE_URL`: hosted Supabase project URL
- `VITE_SUPABASE_ANON_KEY`: hosted Supabase publishable/anon key

Only the public browser key belongs in the frontend. Never put a service-role key or provider API key in a `VITE_*` variable.

### Render — backend

- Repository: `SiddharthaOG/AnchorDraft`
- Root directory: `engine/`
- Python version: set `PYTHON_VERSION=3.12.10`
- Build command: `pip install -e .`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Configure the backend variables listed in [engine/README.md](engine/README.md) and `engine/.env.example`. In staging/production:
- Set `ENVIRONMENT=staging` or `production`.
- Set `LLM_PROVIDER` to a real configured provider (`groq` or `gemini`); `fake` is rejected outside local/test environments.
- Configure the matching primary provider key.
- If fallback is enabled, configure the fallback provider and its key as well.
- Set exact allowed frontend origins in `ALLOWED_ORIGINS`.
- Set the database, Supabase service-role and JWT verification values.
- Generate and securely store `PREVIEW_ENCRYPTION_KEY` for confidentiality preview processing.

Do not use `supabase db reset --remote` against production. Review and apply database changes through the migration workflow.

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Current system architecture, trust boundaries and workflows |
| [Data Model](docs/DATA_MODEL.md) | Database entities, relationships and workflow functions |
| [API Contract](docs/API_CONTRACT.md) | API and data-access contract |
| [Review Engine](docs/REVIEW_ENGINE.md) | Review pipeline, validation and provider behaviour |
| [Engine setup](engine/README.md) | Backend configuration, local run and deployment |
| [Supabase migrations](supabase/migrations/README.md) | Local schema setup, migrations and seed data |
| [AI development log](docs/ai-log/log.md) | Development activity and disclosure |
| [Architecture decisions](docs/ai-log/decisions.md) | Recorded project decisions |
| [Disclosure](docs/DISCLOSURE.md) | Project disclosure information |

## Security notes

- Never commit `.env` files, Supabase service-role keys, JWT signing secrets, provider keys, or generated encryption keys.
- The frontend uses only the Supabase public anon/publishable key.
- Backend endpoints verify Supabase JWTs and enforce role and organisation checks.
- Do not use real confidential content with free-tier external AI accounts unless the applicable provider terms and organisation policy have been reviewed.
- Demo credentials are intentionally not stored in this repository.

## License

MIT — see [LICENSE](LICENSE).

<div align="center">

*Anchor your brand before you publish.* ⚓

</div>
