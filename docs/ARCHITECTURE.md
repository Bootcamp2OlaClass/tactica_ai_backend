# Architecture

## System overview

```
                         ┌─────────────────────┐
                         │   Next.js frontend    │  (tactica_ai_frontend)
                         └──────────┬───────────┘
                                    │ HTTPS (JSON / SSE)
                         ┌──────────▼───────────┐
                         │   FastAPI backend      │  app/main.py
                         │  (routers -> services   │
                         │   -> repositories)      │
                         └───┬──────────┬─────────┘
                              │          │
              ┌───────────────┘          └───────────────┐
   ┌──────────▼──────────┐                   ┌────────────▼────────────┐
   │ PostgreSQL + pgvector │                   │  Redis (broker+backend)  │
   │ (SQLAlchemy/Alembic)  │                   └────────────┬────────────┘
   └───────────────────────┘                                │
                                                   ┌──────────▼──────────┐
                                                   │  Celery worker(s)     │
                                                   │  + Celery beat        │
                                                   │  (queues: system,     │
                                                   │  documents, ai,       │
                                                   │  notifications,       │
                                                   │  calendar)            │
                                                   └───────────────────────┘
        External, all behind a provider interface (never called directly):
        StorageProvider (local disk / Cloudflare R2) · LLMProvider (Gemini / OpenAI)
        EmbeddingProvider (Gemini / OpenAI) · CalendarProvider (Google Calendar)
        NotificationProvider (Resend)
```

## Layering

Every feature follows the same three-layer shape, no exceptions:

- **Router** (`app/routers/*.py`) — HTTP concerns only: request/response schemas, status codes, auth dependency wiring. Never talks to the DB directly.
- **Service** (`app/services/*.py`) — business logic, orchestration, the actual decisions ("is this task overdue," "does this reference a real course," "has this token expired"). Depends on repositories, never on `Request`/`Response` objects.
- **Repository** (`app/repositories/*.py`) — the only layer that writes SQLAlchemy queries. Every ownership check lives here, as a `WHERE` clause, not as an application-level filter applied after fetching — see `docs/SECURITY.md`.

This is a hand-rolled pattern, not a framework's — no LlamaIndex/LangChain (ADR-003), no ORM-magic authorization layer. Deliberate: ownership/tenant-isolation code this security-critical should be a plain, auditable SQL filter a reviewer can read directly, not something routed through a third-party abstraction.

## Provider abstraction pattern

Every integration with an external system (storage, LLM, embeddings, calendar, email) follows the identical shape, first established in Phase 03 and reused five times since:

```
app/services/<domain>/
  base.py       # ABC defining the interface
  exceptions.py # NotConfiguredError / TransientError / ProviderError
  factory.py    # get_<domain>_provider(settings) -- lazy, reads env config
  <vendor>_provider.py  # real implementation, built directly against the
                          # vendor's REST API via httpx (not a heavy SDK)
```

Two consequences that show up throughout the codebase:
- **Unconfigured is not a startup failure.** The app boots fine with zero LLM/R2/Calendar/Resend credentials — a `NotConfiguredError` is only raised at the moment a feature is actually used, and every caller of an optional feature (chat, roadmap generation, recovery-plan explanations) catches it and degrades gracefully rather than failing the whole request.
- **Every real provider is swappable for a fake one in tests** with the exact same call contract, so business logic (grounding, retry behavior, idempotency) is fully tested without needing live credentials. Real-provider network calls remain the one category of thing this test suite cannot prove — tracked explicitly as `NOT VERIFIED` per feature in the project's internal status tracking, never silently assumed.

## Deterministic-first, LLM-second

Every feature that combines deterministic logic with an LLM call (roadmap generation, recovery-plan explanations, degree-course recommendations, AI Study Coach chat) follows the same pipeline:

1. **Compute the deterministic result first**, using only real data already in the database (due dates, calendar math, prerequisite satisfaction, retrieved document chunks). This step never depends on LLM availability and is what the feature's actual acceptance criteria are checked against.
2. **The LLM adds explanation/prioritization/recommendation on top**, constrained to an explicit allow-list of real IDs (`task_id`, `course_code`, `chunk_id`) drawn from step 1.
3. **Ground-truth-filter**: every reference the model proposes is re-verified against the exact set of real entities shown to it that call. An invalid reference is stripped (if the surrounding text can stand alone) or the whole item is dropped (if it can't) — never trusted at face value.
4. **If the LLM is unconfigured or fails**, the deterministic result from step 1 is still returned. A `recommendations_unavailable_reason` field (or equivalent) records why, rather than the feature silently pretending nothing was skipped.

This pattern is why, for example, a semester roadmap generates correctly (with real weeks, real deadlines) even with zero LLM credentials configured — see `docs/AI_RAG_ARCHITECTURE.md` for the retrieval-specific version of this same idea.

## Background jobs

Celery + Redis (ADR-005), chosen over FastAPI's built-in `BackgroundTasks` (no durability/retry/scaling across restarts) and over RQ/arq/DB-polling (weaker scheduling, or an asyncio-model mismatch with this codebase's synchronous SQLAlchemy). Five named queues (`system`, `documents`, `ai`, `notifications`, `calendar`) — the worker must be started with `-Q` listing every one of them explicitly (a real gap found and fixed in Phase 05, BUG-015: a worker that only consumes the default queue silently never executes a task routed elsewhere). `celery beat` (Phase 13) is a *separate* process from the worker, required only for the one periodic job in the codebase (`notifications.send_task_reminders`, every 15 minutes) — the worker alone will never fire anything on a schedule.

Every Celery task in this codebase follows the same idempotent-claim pattern: an atomic "claim" update (`UPDATE ... WHERE status = 'PENDING' RETURNING id`) before doing real work, so retries and duplicate deliveries can't double-process the same row.

## Authentication

Custom hardened JWT (ADR-001, not Clerk despite what the product's original target-architecture table said) — access token in memory on the frontend, refresh token in an httpOnly cookie with rotation and reuse-family revocation, per-account lockout, password reset, email verification, and (Phase 14) account deletion + per-IP/per-user rate limiting. See `docs/SECURITY.md`.

## Where this diverges from the originally-documented target architecture

The product's original target-architecture brief named Clerk (auth), LangChain/LlamaIndex (AI), and Railway (hosting). Actual implementation: custom JWT (ADR-001), hand-rolled retrieval (ADR-003), hosting undecided (ADR-009, still `PROPOSED`, nothing deployed anywhere). Each divergence is a deliberate, recorded engineering decision, not drift — this summary states the outcome; the full options-considered reasoning for each is kept in the project's internal architecture decision log, not this repository.

## Frontend

Next.js (App Router), TypeScript, Tailwind. In-memory access token + httpOnly refresh cookie (never `localStorage`), silent refresh on load via `AuthGuard`. No state-management library beyond React's own — every page fetches through a small `services/*.ts` + `hooks/use*.ts` layer talking to the backend's real JSON contract, with mapper functions translating API shapes to frontend types at the boundary (not duplicated ad hoc per component).
