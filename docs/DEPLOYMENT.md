# Deployment

## Production: Railway

Backend is deployed on Railway (ADR-009 superseded — Railway chosen over Render). Config lives in `railway.json` (build/deploy) plus dashboard-managed env vars; there is no Procfile or shell entrypoint script.

| Setting | Value |
|---|---|
| Build | Dockerfile (`railway.json` → `build.builder: DOCKERFILE`) |
| Pre-deploy command | `alembic upgrade head` — runs once per deploy, on a single instance, before it's promoted live. This is the *only* place migrations run in production. |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — no migration step here, so a crash-looping container never replays migrations, and horizontal replicas never race each other running them. |
| Health check path | `/health` |

**Do not** add `alembic upgrade head &&` back into the start command, and do not configure a second Railway service (worker/beat) with its own copy of the migration step — either reintroduces concurrent `alembic upgrade head` runs against the same Postgres instance, which is what produced the out-of-dependency-order migration log (interleaved output from two racing processes) that motivated this section.

Required env vars, set from Railway's plugin reference syntax rather than hand-typed values so they always match the actual plugin instance:

- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_URL` — from the Postgres plugin (`${{Postgres.PGHOST}}`, `${{Postgres.PGPORT}}`, `${{Postgres.PGDATABASE}}`, `${{Postgres.PGUSER}}`, `${{Postgres.PGPASSWORD}}`, `${{Postgres.DATABASE_URL}}`). All six are required at process start (`app/core/config.py` fails fast if any is missing) — Railway's Postgres plugin does not auto-populate them onto another service, they must be wired explicitly per-service.
- `JWT_SECRET` — real production secret, not the `.env.example` placeholder.
- `CORS_ALLOWED_ORIGINS` — the deployed frontend origin(s).
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` — from the Redis plugin (`${{Redis.REDIS_URL}}`). Unlike the `DATABASE_*` vars these are **not** required — `app/core/config.py` silently falls back to `redis://localhost:6379/0` if unset. On Railway that fallback just fails to connect rather than crashing the API (`/health`'s `redis` field is informational only, see below), but it silently breaks Celery task dispatch/results — set these explicitly on every service (API *and* worker *and* beat) that touches Celery.
- AI/storage/calendar/email vars remain optional exactly as in local dev (see `.env.example`).

If a separate Celery worker/beat deployment is needed on Railway, give each its own service pointed at the same repo/image, with its own start command (`celery -A app.worker.celery_app worker -Q ...` / `celery -A app.worker.celery_app beat`) and **no** pre-deploy command — only the API service should run migrations.

## Local development (`docker compose up --build`)

`compose.yaml` (identical copies kept in sync in both repos — a convention every infra-touching phase since Phase 04 has followed) brings up five services:

| Service | What it runs | Depends on |
|---|---|---|
| `frontend` | `npm run dev` (Next.js), port 3000 | `backend` |
| `backend` | `alembic upgrade head && uvicorn app.main:app --reload`, port 8000 | `db`, `redis` (healthy) |
| `worker` | `celery -A app.worker.celery_app worker -Q system,documents,ai,notifications,calendar` | `db`, `redis`, `backend` (all healthy) |
| `beat` | `celery -A app.worker.celery_app beat` (Phase 13, the only periodic job's scheduler) | `db`, `redis`, `backend` (all healthy) |
| `redis` | `redis:7-alpine`, port 6379 | — |
| `db` | `pgvector/pgvector:pg16`, port `${DATABASE_PORT}` | — |

Shared named volume `uploads_data` mounted into both `backend` and `worker` — without it, a file the API saves is invisible to the worker container that needs to read it back for processing (found live in Phase 05, BUG-016: separate containers have separate filesystems by default).

`backend` runs migrations before serving, and has a healthcheck (only passes once uvicorn is actually accepting requests, i.e. strictly after migrations finish) that `worker`/`beat` wait on — a fresh `docker compose up` against an empty `postgres_data` volume previously left the schema completely empty, since nothing in the stack ever ran `alembic upgrade head` (BUG-021, found and fixed via a real `docker compose down -v && up` run during release-candidate verification — the same class of gap only a genuine multi-container run can surface, per Phase 05's precedent).

Required env vars (see `.env.example` in the backend repo): `DATABASE_*`, `JWT_SECRET`, `CORS_ALLOWED_ORIGINS`. Everything else (LLM/embedding/R2/Calendar/Resend credentials) is optional — every provider abstraction degrades gracefully to "feature unavailable" rather than failing startup when unconfigured (see `docs/ARCHITECTURE.md`).

Running the API standalone (`uvicorn app.main:app --reload`, no Docker) works for anything that doesn't need a background job — auth, CRUD, dashboard. Document processing, extraction, embedding, roadmap generation, and notifications all require a real `worker` process (and `beat`, for notifications specifically) actually running and subscribed to the right queues.

## CI (Phase 15)

`.github/workflows/backend-ci.yml` and `.github/workflows/frontend-ci.yml`, triggered on `pull_request`/`push` to `main`/`develop`. Backend: install, pytest against real `pgvector`/Redis GitHub Actions service containers, `alembic upgrade head` + `alembic check`. Frontend: `npm ci`, lint, typecheck, test (Vitest), build. Both verified via exact local command reproduction; **neither has been exercised by an actual GitHub Actions run** — this environment has no `gh` CLI or repo-admin/Actions access to trigger or observe one. Branch protection (requiring these checks before merge) is similarly not configured, for the same access reason.

A real Playwright E2E test exists (`frontend/e2e/critical-path.spec.ts`) and was run for real against a live local stack this session — document processing and AI features are deliberately out of scope for the current E2E pass (see the test file's own header comment for exactly what it covers and why).

## What's still outstanding

- **Real credentials** for every optional provider currently unconfigured in production: R2 (or a chosen storage backend), Gemini/OpenAI, Google Calendar OAuth app registration, Resend.
- **`NEXT_PUBLIC_API_BASE_URL` baked in at frontend build time** — Next.js inlines `NEXT_PUBLIC_*` vars at build, not runtime, so the frontend Docker image needs a build-arg passthrough that doesn't exist yet (tracked from Phase 00's original audit, BUG-009's note — the backend image's own rebuild is verified via Phase 04/05's `docker compose up --build`; the frontend image specifically has not been exercised this way).
- **Branch protection + a real CI run**, per above.
- **Frontend hosting** (Vercel or equivalent) — not yet set up; only the backend is deployed so far.

## Health check

`GET /health` reports `{"status": "healthy", "redis": "connected"|"unreachable"}`. Redis being unreachable does **not** fail this check or the request — Redis/Celery are optional infrastructure for the API itself to be considered "up" (synchronous CRUD works with zero worker running); this is intentional, documented in `app/main.py` at the point of definition, not an oversight.
