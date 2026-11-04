# Disclosure Log

This file records all libraries, services, templates, and reused material used in this project, as required by the competition rules.

## Libraries

### Engine (Python)

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| fastapi | 0.162.0 | MIT | Web framework |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server |
| pydantic | 2.14.2 | MIT | Data validation |
| pydantic-settings | 2.16.2 | MIT | Settings management (BaseSettings for env config) |
| python-dotenv | 1.2.4 | BSD-3-Clause | Environment loading (loads .env into os.environ) |
| pytest | 9.2.0 | MIT | Testing framework |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Async testing (pytest fixtures for async code) |
| httpx | 0.28.1 | MIT | HTTP client for tests |

### Web (JavaScript/TypeScript)

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| react | 19.3.1 | MIT | UI library |
| react-dom | 19.3.1 | MIT | DOM renderer |
| vite | 8.3.5 | MIT | Build tool |
| @vitejs/plugin-react | 6.1.2 | MIT | React plugin for Vite |
| tailwindcss | 4.3.4 | MIT | CSS framework |
| typescript | 7.0.2 | Apache-2.0 | Type system |
| vitest | 3.1.1 | MIT | Testing framework |

## Services

| Service | Purpose |
|---------|---------|
| Supabase | Database, Auth, Storage, Realtime |
| Vercel | Web app hosting |
| Render | Engine hosting |
| Google Gemini (or Groq) | LLM provider (future slices) |

## Templates & Patterns

- Vite React TypeScript starter structure (official Vite template)
- FastAPI project structure (official FastAPI documentation)
- Tailwind CSS 4 Vite integration (official Tailwind documentation)

## AI Assistance

This project was developed with AI assistance (Nemotron 3 Ultra via OpenCode). All code was reviewed and approved by the human architect.