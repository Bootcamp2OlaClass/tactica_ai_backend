# API Reference

All endpoints except `/`, `/health`, and `/auth/register|login|refresh|password-reset/*|verify-email/confirm` require a bearer access token (`Authorization: Bearer <token>`), obtained from `/auth/login` or `/auth/register` and refreshed via `/auth/refresh` (httpOnly cookie). Interactive docs are always available at `/docs` (Swagger) and `/redoc` when the server is running — this file is a stable reference for the shape of the API, not a substitute for it.

Every list/detail endpoint scopes results to the authenticated user; see `docs/SECURITY.md` for how ownership is enforced (audited in Phase 14, zero IDOR findings across every router below).

## Authentication (`/auth`)

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | Issues an access token + sets an httpOnly refresh cookie. Rate-limited (5/min/IP). |
| POST | `/auth/login` | Same token/cookie shape. Per-account lockout after 5 failed attempts (15 min); rate-limited (20/min/IP). |
| POST | `/auth/refresh` | Rotates the refresh token (reuse of an already-rotated token revokes the whole token family — theft detection). |
| POST | `/auth/logout` | Revokes the current refresh token, clears the cookie. |
| GET | `/auth/me` | Current user's profile. |
| POST | `/auth/password-reset/request` | Always returns 200 regardless of whether the email exists (no account enumeration). Rate-limited (5/min/IP). |
| POST | `/auth/password-reset/confirm` | Consumes a one-time token, revokes every existing session. |
| POST | `/auth/verify-email/resend` | Rate-limited (5/min/IP). |
| POST | `/auth/verify-email/confirm` | |
| DELETE | `/auth/account` | Requires the current password in the body. Soft-deletes + anonymizes the account, revokes every session (Phase 14). |

## Semesters (`/api/v1/semesters`)

| Method | Path |
|---|---|
| POST | `/api/v1/semesters` |
| GET | `/api/v1/semesters` |
| GET | `/api/v1/semesters/{semester_id}` |
| PATCH | `/api/v1/semesters/{semester_id}` |
| DELETE | `/api/v1/semesters/{semester_id}` |

## Courses (`/api/v1`)

| Method | Path |
|---|---|
| POST | `/api/v1/semesters/{semester_id}/courses` |
| GET | `/api/v1/semesters/{semester_id}/courses` |
| GET | `/api/v1/courses` |
| GET | `/api/v1/courses/{course_id}` |
| PATCH | `/api/v1/courses/{course_id}` |
| DELETE | `/api/v1/courses/{course_id}` |

## Tasks (`/api/v1`)

| Method | Path |
|---|---|
| POST | `/api/v1/courses/{course_id}/tasks` |
| GET | `/api/v1/tasks` | Filterable by `course_id`/`semester_id`/status; always scoped to the caller. |
| GET | `/api/v1/tasks/{task_id}` |
| PATCH | `/api/v1/tasks/{task_id}` |
| POST | `/api/v1/tasks/{task_id}/complete` |
| POST | `/api/v1/tasks/{task_id}/reopen` |
| DELETE | `/api/v1/tasks/{task_id}` | Non-fatally unsyncs any Calendar event for the task first. |

## Documents (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/courses/{course_id}/documents` | Multipart upload; PDF only, 10MB default cap (`MAX_UPLOAD_SIZE`). |
| GET | `/api/v1/courses/{course_id}/documents` | |
| GET | `/api/v1/documents/{document_id}` | |
| GET | `/api/v1/documents/{document_id}/download` | Streams bytes through the authenticated backend (no presigned URL). |
| POST | `/api/v1/documents/{document_id}/reprocess` | Re-enqueues extraction; `202 Accepted`. |
| DELETE | `/api/v1/documents/{document_id}` | |

## Extraction (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/documents/{document_id}/extract` | Enqueues the LLM structured-extraction Celery task. |
| GET | `/api/v1/documents/{document_id}/extraction-candidates` | |
| POST | `/api/v1/extraction-candidates/{candidate_id}/accept` | Creates a real `Task`, or fills a blank `Course` field — nothing auto-commits before this call (ADR-006). |
| POST | `/api/v1/extraction-candidates/{candidate_id}/reject` | |

## RAG (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/documents/{document_id}/embed` | Enqueues chunk+embed. |

## Chat / AI Study Coach (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/chat` | Retrieve->Generate->Validate->Ground-truth-filter->Return. Per-user rate limit (20/min — the app's one synchronous LLM call in the request path). |
| POST | `/api/v1/chat/stream` | Same pipeline, Server-Sent Events. Same rate limit. |
| GET | `/api/v1/chat/conversations` | |
| GET | `/api/v1/chat/conversations/{conversation_id}` | |

## Semester Roadmap (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/semesters/{semester_id}/roadmap/generate` | `202 Accepted`, async (Celery). Deterministic items always generated even with no LLM configured. |
| GET | `/api/v1/semesters/{semester_id}/roadmap` | |
| PATCH | `/api/v1/roadmap-items/{item_id}` | Sets `is_user_edited`; edits survive future regenerations. |

## Recovery Plan (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/recovery-plan` | Compute-on-demand, no persistence. Deterministic priority ordering; LLM only adds explanation text. |

## Degree Advisor (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/degree-progress/declare` | |
| GET | `/api/v1/degree-progress` | Eligible-course recommendations only ever come from the deterministically-validated eligible set. |

## Calendar (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/calendar/authorize` | Returns the Google OAuth authorization URL. |
| POST | `/api/v1/calendar/connect` | Exchanges an OAuth code for tokens (encrypted at rest, Phase 14). |
| DELETE | `/api/v1/calendar/disconnect` | |
| GET | `/api/v1/calendar/status` | |
| POST | `/api/v1/tasks/{task_id}/calendar-sync` | Idempotent — creates once, updates on every subsequent call. |
| DELETE | `/api/v1/tasks/{task_id}/calendar-sync` | |

## Notifications (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/notification-preferences` | |
| PUT | `/api/v1/notification-preferences/{notification_type}` | Opt-out model — no row means enabled. |

## Dashboard

| Method | Path |
|---|---|
| GET | `/api/v1/dashboard` |

## System

| Method | Path | Notes |
|---|---|---|
| GET | `/` | |
| GET | `/health` | Reports Postgres/Redis status; Redis being down does not fail the check (see `docs/ARCHITECTURE.md`). |

## Error shape

Every non-2xx response is `{"detail": "..."}` (or FastAPI's standard 422 validation-error body for request-shape errors). Unhandled exceptions are caught by `app/main.py`'s logging middleware and returned as a generic `500 {"detail": "Internal server error"}` — stack traces are never exposed to the client (see `docs/SECURITY.md`).
