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
- **`OPENAI_JSON_OBJECT`** — defaults to **`1`**. When enabled, requests use `response_format: json_object` (helps structured output on OpenAI-compatible APIs). Set to **`0`** if your provider rejects that parameter.

**Environment files:** Put secrets and LLM settings in a **project `.env`** file next to `docker-compose.yml` (copy from `.env.example`). The backend service uses Compose **`env_file: .env`** so `OPENAI_API_KEY` is taken **from that file** into the container.

**Important:** Do **not** rely on a shell `export OPENAI_API_KEY=...` for the API key unless you know what you are doing. For `OPENAI_API_KEY`, a value exported in the shell (for example an old placeholder like `YOUR_KEY_HERE`) can override the project `.env` when using pass-through env—this project **does not** pass `OPENAI_API_KEY` through the shell for that reason; use `.env` for the key. Optional vars like `OPENAI_BASE_URL` may still be overridden by the shell—see `docker-compose.yml`.

Set `OPENAI_API_KEY` to the secret issued by your provider. Never commit `.env`.

**Stub mode (default)**

```bash
docker compose up --build
```

With `LLM_MODE=stub` or unset in `.env` / environment (default in Compose is `stub`).

**Real mode (requires a key)**

Either set variables in `.env`:

```bash
cp .env.example .env
# Edit .env: set LLM_MODE=real and OPENAI_API_KEY=<your real API key>
docker compose up --build
```

Or export in the shell (no `.env` required):

```bash
export LLM_MODE=real
export OPENAI_API_KEY="..."   # value from your provider
docker compose up --build
```

If `LLM_MODE=real` and `OPENAI_API_KEY` is **unset**, **empty**, or **whitespace-only** after trim, `POST /process` returns **503** (configuration error; **no** provider call). The backend does **not** inspect key contents. Invalid or revoked keys may still yield **502** from the provider after a call.

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
