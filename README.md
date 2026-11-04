# AnchorDraft

Pre-publication brand-governance platform for startups.

## Repository Structure

```
anchordraft/
├── docs/                 # Design documents and AI logs
├── supabase/migrations/  # Database migrations
├── engine/               # FastAPI review service
│   ├── app/
│   └── tests/
└── web/                  # Vite + React + TypeScript + Tailwind CSS 4
    └── src/
```

## Quick Start

### Prerequisites

- Node.js 20.19+ or 22.12+ (Vite 8 requirement)
- Python 3.11+ (FastAPI 0.162 requirement)
- uv (recommended) or pip

### Engine (FastAPI)

```bash
cd engine
cp .env.example .env
# Edit .env with your values
uv sync --extra test  # or: pip install -e ".[test]"
uv run uvicorn app.main:app --reload
```

The engine will be available at `http://localhost:8000/v1/health`.

### Web (Vite + React)

```bash
cd web
cp .env.example .env
# Edit .env with your values
npm install
npm run dev
```

The web app will be available at `http://localhost:5173` and will call the engine at `VITE_ENGINE_URL`.

### Running Tests

```bash
# Engine tests (from engine/ directory)
cd engine
uv run pytest -v

# Web tests
cd web
npm run test
```

## Deployment

### Vercel (Web)

1. Connect this repository to Vercel
2. Set root directory to `web/`
3. **Node.js version**: Vercel reads `engines.node` in `package.json` ([docs](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions): "You can define the major Node.js version in the `engines#node` section of the `package.json` to override the one you have selected in the Project Settings"). This repo sets `"engines": {"node": "22.x"}` in `web/package.json`.
4. Add environment variables from `web/.env.example`:
   - `VITE_ENGINE_URL=https://your-engine.onrender.com`
   - `VITE_SUPABASE_URL=...`
   - `VITE_SUPABASE_ANON_KEY=...`
5. Deploy

### Render (Engine)

1. Create a new Web Service on Render
2. Connect this repository
3. Set root directory to `engine/`
4. **Python version**: Render's docs state: "Set your service's `PYTHON_VERSION` environment variable to a fully qualified Python version (e.g., `3.13.5`). You can specify any released version from `3.7.3` onward" ([docs](https://render.com/docs/python-version)). **Reasoning**: The `.python-version` file is read from the repo root, but since the service root is `engine/`, set the Render environment variable `PYTHON_VERSION=3.12.10`.
5. Build command: `pip install -e .` (runtime deps only, no test extras)
6. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
7. Add environment variables from `engine/.env.example`:
   - `VERSION=0.1.0`
   - `ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:5173`
   - `SUPABASE_URL=...`
   - `SUPABASE_SERVICE_ROLE_KEY=...`
   - `LLM_PROVIDER=fake`
   - `LLM_MODEL=`
   - `DAILY_REVIEW_CAP=20`
   - `PYTHON_VERSION=3.12.10`
8. Deploy

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [API Contract](docs/API_CONTRACT.md)
- [Review Engine](docs/REVIEW_ENGINE.md)
- [AI Log](docs/ai-log/log.md)
- [Decisions](docs/ai-log/decisions.md)
- [Disclosure](docs/DISCLOSURE.md)

## License

MIT