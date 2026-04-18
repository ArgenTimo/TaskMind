# TaskMind

Minimal AI Work Assistant MVP: FastAPI backend, React (Vite) frontend, Docker Compose runtime.

## Prerequisites

- Docker with Compose v2 (`docker compose`)

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

### 2) Backend process (valid request)

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

Expected: all tests pass (health, valid `/process`, invalid mode).

### 5) Frontend

Open `http://localhost:5173` in a browser. Enter text, choose a mode (`analyze`, `reply`, or `extract_tasks`), and click **Submit**. The summary, intent, reply, and tasks sections should populate without CORS errors in the developer console.

### Stop

```bash
docker compose down
```

## Configuration

- **CORS:** Backend allows `http://localhost:5173` and `http://127.0.0.1:5173` by default. Override with `FRONTEND_ORIGIN` (comma-separated list) if needed.
- **Frontend API URL:** Defaults to `http://localhost:8000` via `VITE_API_URL` in Compose (suitable when the browser runs on the host and ports are published as above).

## Project docs

See `AGENTS.md` and `docs/` for product and architecture notes.
