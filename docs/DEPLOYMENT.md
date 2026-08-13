# Deployment

## Current state: nothing is deployed anywhere

Production hosting has not been decided (ADR-009, status `PROPOSED`) or implemented. This document describes the only environment that's real today — local Docker Compose — plus CI, and is explicit about what remains undecided rather than describing an aspirational target as if it existed.

## Local development (`docker compose up --build`)

`compose.yaml` (identical copies kept in sync in both repos — a convention every infra-touching phase since Phase 04 has followed) brings up five services:

| Service | What it runs | Depends on |
|---|---|---|
| `frontend` | `npm run dev` (Next.js), port 3000 | `backend` |
| `backend` | `uvicorn app.main:app --reload`, port 8000 | `db`, `redis` (healthy) |
| `worker` | `celery -A app.worker.celery_app worker -Q system,documents,ai,notifications,calendar` | `db`, `redis` (healthy) |
| `beat` | `celery -A app.worker.celery_app beat` (Phase 13, the only periodic job's scheduler) | `db`, `redis` (healthy) |
| `redis` | `redis:7-alpine`, port 6379 | — |
| `db` | `pgvector/pgvector:pg16`, port `${DATABASE_PORT}` | — |

Shared named volume `uploads_data` mounted into both `backend` and `worker` — without it, a file the API saves is invisible to the worker container that needs to read it back for processing (found live in Phase 05, BUG-016: separate containers have separate filesystems by default).

Required env vars (see `.env.example` in the backend repo): `DATABASE_*`, `JWT_SECRET`, `CORS_ALLOWED_ORIGINS`. Everything else (LLM/embedding/R2/Calendar/Resend credentials) is optional — every provider abstraction degrades gracefully to "feature unavailable" rather than failing startup when unconfigured (see `docs/ARCHITECTURE.md`).

Running the API standalone (`uvicorn app.main:app --reload`, no Docker) works for anything that doesn't need a background job — auth, CRUD, dashboard. Document processing, extraction, embedding, roadmap generation, and notifications all require a real `worker` process (and `beat`, for notifications specifically) actually running and subscribed to the right queues.

## CI (Phase 15)

`.github/workflows/backend-ci.yml` and `.github/workflows/frontend-ci.yml`, triggered on `pull_request`/`push` to `main`/`develop`. Backend: install, pytest against real `pgvector`/Redis GitHub Actions service containers, `alembic upgrade head` + `alembic check`. Frontend: `npm ci`, lint, typecheck, test (Vitest), build. Both verified via exact local command reproduction; **neither has been exercised by an actual GitHub Actions run** — this environment has no `gh` CLI or repo-admin/Actions access to trigger or observe one. Branch protection (requiring these checks before merge) is similarly not configured, for the same access reason.

A real Playwright E2E test exists (`frontend/e2e/critical-path.spec.ts`) and was run for real against a live local stack this session — document processing and AI features are deliberately out of scope for the current E2E pass (see the test file's own header comment for exactly what it covers and why).

## What a real deployment needs (not yet done)

- **A hosting decision** (ADR-009) — Railway vs. Render for backend/worker/beat, a managed Postgres with `pgvector` availability confirmed, managed Redis, Vercel (or equivalent) for the frontend.
- **Real credentials** for every optional provider currently unconfigured in this environment: R2 (or a chosen storage backend), Gemini/OpenAI, Google Calendar OAuth app registration, Resend.
- **A production `JWT_SECRET`** and every other secret currently only present as a local `.env` value.
- **`NEXT_PUBLIC_API_BASE_URL` baked in at frontend build time** — Next.js inlines `NEXT_PUBLIC_*` vars at build, not runtime, so the frontend Docker image needs a build-arg passthrough that doesn't exist yet (tracked from Phase 00's original audit, BUG-009's note — the backend image's own rebuild is verified via Phase 04/05's `docker compose up --build`; the frontend image specifically has not been exercised this way).
- **Branch protection + a real CI run**, per above.

## Health check

`GET /health` reports `{"status": "healthy", "redis": "connected"|"unreachable"}`. Redis being unreachable does **not** fail this check or the request — Redis/Celery are optional infrastructure for the API itself to be considered "up" (synchronous CRUD works with zero worker running); this is intentional, documented in `app/main.py` at the point of definition, not an oversight.
