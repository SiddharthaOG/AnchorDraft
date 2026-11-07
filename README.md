<div align="center">

# ⚓ AnchorDraft

*Pre-publication brand-governance platform for startups.*

![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-Backend-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-20.19+-339933?style=for-the-badge&logo=node.js&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

<img src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&h=300&fit=crop" alt="AnchorDraft Banner" width="800" />

</div>

---

## 📁 Repository Structure

```text
anchordraft/
├── docs/                 # Design documents and AI logs
├── supabase/migrations/  # Database migrations
├── engine/               # FastAPI review service
│   ├── app/
│   └── tests/
└── web/                  # Vite + React + TypeScript + Tailwind CSS 4
    └── src/
```

---

## 🚀 Quick Start

### Prerequisites

![Node.js](https://img.shields.io/badge/Node.js-20.19+_or_22.12+-339933?style=flat-square&logo=node.js&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-recommended-de4c9f?style=flat-square)

- Node.js 20.19+ or 22.12+ (Vite 8 requirement)
- Python 3.11+ (FastAPI 0.162 requirement)
- uv (recommended) or pip

---

### ⚙️ Engine (FastAPI)

```bash
cd engine
cp .env.example .env
# Edit .env with your values
uv sync --extra test  # or: pip install -e ".[test]"
uv run uvicorn app.main:app --reload
```

> ✅ The engine will be available at `http://localhost:8000/v1/health`.

---

### 🌐 Web (Vite + React)

```bash
cd web
cp .env.example .env
# Edit .env with your values
npm install
npm run dev
```

> ✅ The web app will be available at `http://localhost:5173` and will call the engine at `VITE_ENGINE_URL`.

---

### 🧪 Running Tests

```bash
# Engine tests (from engine/ directory)
cd engine
uv run pytest -v

# Web tests
cd web
npm run test
```

---

## 📦 Deployment

### Vercel (Web)

![Vercel](https://img.shields.io/badge/Platform-Vercel-000000?style=flat-square&logo=vercel&logoColor=white)

1. Connect this repository to Vercel
2. Set root directory to `web/`
3. **Node.js version**: Vercel reads `engines.node` in `package.json` ([docs](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions): "You can define the major Node.js version in the `engines#node` section of the `package.json` to override the one you have selected in the Project Settings"). This repo sets `"engines": {"node": "22.x"}` in `web/package.json`.
4. Add environment variables from `web/.env.example`:
   - `VITE_ENGINE_URL=https://your-engine.onrender.com`
   - `VITE_SUPABASE_URL=...`
   - `VITE_SUPABASE_ANON_KEY=...`
5. Deploy

---

### Render (Engine)

![Render](https://img.shields.io/badge/Platform-Render-46E3B7?style=flat-square&logo=render&logoColor=white)

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

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| 📐 [Architecture](docs/ARCHITECTURE.md) | System architecture overview |
| 🗄️ [Data Model](docs/DATA_MODEL.md) | Database schema and models |
| 📡 [API Contract](docs/API_CONTRACT.md) | API specifications and endpoints |
| 🤖 [Review Engine](docs/REVIEW_ENGINE.md) | Review engine internals |
| 📝 [AI Log](docs/ai-log/log.md) | AI development log |
| 🧠 [Decisions](docs/ai-log/decisions.md) | Architectural decision records |
| 🔍 [Disclosure](docs/DISCLOSURE.md) | Project disclosure information |

---

## 📄 License

This project is licensed under the **MIT** License.

![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

---

<div align="center">

*Anchor your brand before you publish.* ⚓

</div>
