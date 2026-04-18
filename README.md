# TaskMind

Minimal AI Work Assistant MVP: FastAPI backend, React (Vite) frontend, Docker Compose runtime.

## Prerequisites

- Docker with Compose v2 (`docker compose`)

## Configuration (LLM)

The backend reads `LLM_MODE`:

| Value | Behavior |
|--------|----------|
| `stub` (default) | Deterministic local output. **No API key** and **no network call** to an LLM provider. |
| `real` | Calls an **OpenAI-compatible** `POST /v1/chat/completions` endpoint. Requires **`OPENAI_API_KEY`** set to a non-empty string. |

Optional when `LLM_MODE=real`:

- **`OPENAI_BASE_URL`** — defaults to `https://api.openai.com/v1` (other OpenAI-compatible bases may work).
- **`OPENAI_MODEL`** — defaults to `gpt-4o-mini`.

Copy `.env.example` to `.env` at the repo root and set variables as needed. Compose passes these into the backend service (see `docker-compose.yml`).

**Stub mode (default)**

```bash
# optional; stub is the default when LLM_MODE is unset
export LLM_MODE=stub
docker compose up --build
```

**Real mode (requires a key)**

```bash
export LLM_MODE=real
export OPENAI_API_KEY='your-key-here'
docker compose up --build
```

If `LLM_MODE=real` but `OPENAI_API_KEY` is missing or empty, `POST /process` returns **503** with a clear error message (it does not crash the app).

## Run

From the repository root:

```bash
docker compose up --build
```

- Backend API: `http://localhost:8000`
- Frontend (Vite dev server): `http://localhost:5173`

Leave this running for the verification steps below.

## Verify

### 1) Backend health

```bash
curl -sS http://localhost:8000/health
```

Expected: HTTP 200 and JSON `{"status":"ok"}`.

### 2) Backend process (valid request, stub mode)

With default stub configuration:

```bash
curl -sS -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{"text":"hello world","mode":"analyze"}'
```

Expected: HTTP 200 and JSON with keys `summary`, `intent`, `reply`, and `tasks` (array).

### 3) Backend validation (invalid mode)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{"text":"hello","mode":"full"}'
```

Expected: HTTP status code `422`.

### 4) Backend tests (inside the backend container)

In a second terminal, from the repository root:

```bash
docker compose exec backend pytest -q
```

Expected: all tests pass.

### 5) Real mode misconfiguration (optional)

Start stack with `LLM_MODE=real` and **without** `OPENAI_API_KEY`:

```bash
LLM_MODE=real OPENAI_API_KEY= docker compose up --build
```

Then:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{"text":"hello","mode":"analyze"}'
```

Expected: HTTP **503**.

### 6) Frontend

Open `http://localhost:5173` in a browser. Enter text, choose a mode (`analyze`, `reply`, or `extract_tasks`), and click **Submit**. The summary, intent, reply, and tasks sections should populate without CORS errors in the developer console.

### Stop

```bash
docker compose down
```

## Other configuration

- **CORS:** Backend allows `http://localhost:5173` and `http://127.0.0.1:5173` by default. Override with `FRONTEND_ORIGIN` (comma-separated list) if needed.
- **Frontend API URL:** Defaults to `http://localhost:8000` via `VITE_API_URL` in Compose (suitable when the browser runs on the host and ports are published as above).

## Project docs

See `AGENTS.md` and `docs/` for product and architecture notes.
