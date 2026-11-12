# Engine — AnchorDraft Review Service

FastAPI service for review pipeline. Runs on Render.

## Quick Start

```bash
cd engine
cp .env.example .env
# Edit .env with your values
pip install -e ".[test]"
uvicorn app.main:app --reload
```

The service will be available at `http://localhost:8000/v1/health`.

## Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `VERSION` | Service version | `0.1.0` |
| `ALLOWED_ORIGINS` | CORS origins (JSON array or comma-separated) | `http://localhost:5173,http://localhost:3000` |
| `SUPABASE_URL` | Supabase project URL | — |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | — |
| `LLM_PROVIDER` | LLM provider (`fake`, `gemini`, `groq`) | `fake` |
| `LLM_MODEL` | Model name | — |
| `GEMINI_API_KEY` | Google Gemini API key | — |
| `GEMINI_MODEL` | Primary Gemini model | `gemini-3.8-flash` |
| `GEMINI_FALLBACK_MODEL` | Distinct same-key fallback model for transient Gemini failures | `gemini-3.6-flash` |
| `GROQ_API_KEY` | Groq API key | — |
| `DAILY_REVIEW_CAP` | Max reviews per org per day | `20` |

### Review preview encryption

Generate a Fernet key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Place it in the engine environment. Never commit the generated value. Set the same PREVIEW_ENCRYPTION_KEY on every Render engine instance. A key mismatch makes pending previews undecryptable; rotate it only after pending previews have expired or been consumed. The preview migration is supabase/migrations/20261111164322_add_review_previews.sql; apply it through the approved migration workflow before enabling the preview endpoints.

The preview stores only redacted provider prompts and a payload hash. The placeholder reverse map is Fernet-encrypted and cleared after terminal processing. Preview records expire after 10 minutes. If attached images will be sent to the vision provider, the creator must explicitly consent; image bytes are not OCR-redacted.

## Running Tests

```bash
python -m pytest tests/ -v
```

## API

- `GET /v1/health` — Liveness probe. Returns `{status, version, time}`.
- `POST /v1/reviews` — Start a review (requires JWT).
- `POST /v1/imports/text` — Extract text from PDF/DOCX.
- `POST /v1/kits/{kit_id}/lint` — Lint a draft kit.

## CORS

`ALLOWED_ORIGINS` accepts two formats:

1. **JSON array** (preferred): `["https://app.example.com","http://localhost:3000"]`
2. **Comma-separated**: `https://app.example.com,http://localhost:3000`

Both formats are parsed automatically. No wildcard (`*`) is allowed.

## Development

- Uses `pydantic-settings` for config with `.env` file support.
- Settings cached via `lru_cache`; call `clear_settings_cache()` in tests to reload.
- CORS: specific origins only, no wildcard. Allowed headers: `X-Request-Id`, `Authorization`, `Content-Type`.

## Deployment (Render)

- Root directory: `engine/`
- Build command: `pip install -e .`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Python version: set `PYTHON_VERSION=3.12.10` in Render environment variables
- Add all env vars from `.env.example`