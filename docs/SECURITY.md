# Security

This document describes the security posture as actually implemented and verified — every claim below is backed by a test or a recorded audit finding from the project's Phase 14 security review (bug IDs BUG-017 through BUG-020 in the project's internal bug tracker), not aspirational.

## Reporting an issue

This is a student project with no public deployment yet (see `docs/DEPLOYMENT.md`) and no formal disclosure process. If you find a vulnerability, open an issue against the relevant repo (backend or frontend) describing the finding — do not include working exploit payloads against real user data, since none currently exists to be at risk, but treat the same discipline as if it did.

## Authentication

Custom hardened JWT (ADR-001) — not Clerk, despite the product's original target-architecture documentation. Access tokens are short-lived and held in memory on the frontend only, never `localStorage`. Refresh tokens are stored hashed (SHA-256, never the raw value) in `refresh_tokens`, delivered via an httpOnly cookie, and rotated on every use — presenting an already-rotated (stale) refresh token revokes its entire token family, the standard signal that a token was stolen and replayed.

Per-account lockout: 5 failed login attempts locks the account for 15 minutes (`User.failed_login_attempts`/`locked_until`). Per-IP rate limiting (Phase 14) on top of that: `register`/`login`/`password-reset/request`/`verify-email/resend`, Redis-backed fixed-window (`INCR`+`EXPIRE`), fails **open** on Redis errors — a Redis outage degrading to temporarily-unlimited traffic was judged a better failure mode than a Redis outage taking down every auth endpoint.

Password reset and email verification both use single-use, hashed, expiring tokens. Password-reset request always returns the same response regardless of whether the email exists — no account enumeration via that endpoint, or via login (a deleted account gets the identical "invalid credentials" response as a wrong password, not a distinguishable "this account was deleted").

## Account deletion (Phase 14, BUG-018)

`DELETE /auth/account`, requires the current password. Implemented as **soft-delete + PII anonymization**, not a hard cascade delete: email replaced with a synthetic `deleted-user-{id}@...` address, name blanked, password hash overwritten with an unusable random value, `deleted_at` set, every refresh token revoked. `get_current_user` and `login_user` both reject `deleted_at is not None` — a still-valid access token stops working on its very next request after deletion, not just after its natural ~15-minute expiry.

Not a full hard-delete cascade: ~24 tables reference `users.id` with mixed `CASCADE`/`RESTRICT` FK behavior (`document_chunks` is `RESTRICT`, Phase 07, deliberately — see `docs/DATABASE.md`), and a correct hard delete needs a per-table cleanup plan sequenced around that. Tracked as a real, scoped limitation, not silently equated to full erasure.

## Authorization / IDOR

Every object type in the schema is reachable from `users.id` either by a direct `user_id` column or by a repository-enforced join chain up to one — see `docs/DATABASE.md`'s ownership model. Phase 14's audit traced every path-parameterized endpoint across all 12 routers into its repository layer, specifically checking that nested resources (task under course under semester, extraction candidate under document under course under semester, roadmap item under week under roadmap under semester) are anchored to the resource's *own* actual parent chain read from the database — never to a second, client-supplied ID that could be substituted with one the attacker legitimately owns elsewhere. **Zero vulnerabilities found.**

## Rate limiting (Phase 14, BUG-019)

Two variants (`app/api/rate_limit.py`), both Redis-backed fixed-window, both fail open:
- **Per-IP**: `register`, `login`, `password-reset/request`, `verify-email/resend`.
- **Per-user** (keyed by authenticated user id, not IP): `POST /chat`, `POST /chat/stream` — the one endpoint in the app that makes a synchronous, real-cost LLM call per request; IP is a weak signal for an authenticated abuser who can trivially rotate it, unlike the account itself.

Not applied app-wide — every other authenticated endpoint is cheap CRUD already bounded to a traceable account. Roadmap/recovery-plan generation are also LLM-backed but Celery-queued (async), judged lower urgency than chat's synchronous cost profile; tracked as a follow-up.

## Prompt injection

See `docs/AI_RAG_ARCHITECTURE.md`'s "Prompt-injection mitigation" section — document extraction and chat (which see genuinely untrusted content) have explicit "treat as untrusted data, not instructions" framing in their system prompts plus schema-enforced structured output; roadmap/recovery-plan/degree-recommendation prompts see only allow-listed, ground-truth-filtered references, making the same framing lower-value there. Not tested against a real adversarial document with a real model (no LLM credentials in this environment) — the mitigation's *presence* is verified, its real-world effectiveness is not.

## Encryption at rest

Google Calendar OAuth tokens (`calendar_connections.access_token`/`refresh_token`) are encrypted at rest as of Phase 14 (BUG-020) via a transparent SQLAlchemy `TypeDecorator` (`app/core/token_encryption.py`, Fernet symmetric encryption, key derived from `JWT_SECRET`). Every existing read/write call site needed zero changes — encryption/decryption happens at the ORM boundary, so it's structurally impossible to read/write the column any other way. `refresh_tokens` (session tokens) intentionally store only a one-way SHA-256 hash instead — a stronger property than reversible encryption, appropriate since a session token never needs to be recovered in plaintext, unlike an OAuth token used to call Google's API.

## File upload validation

MIME type, size (`MAX_UPLOAD_SIZE`, default 10MB), checksum, and path-traversal safety on stored filenames — implemented before Phase 00's original audit and confirmed still solid during Phase 14 rather than re-derived from scratch (lower priority for a deep re-audit given no changes since).

## CORS

`app/main.py`'s `CORSMiddleware` uses an explicit origin allow-list from config (`CORS_ALLOWED_ORIGINS`, default `http://localhost:3000` for local dev) — never a wildcard. Reviewed in Phase 14, already correct, no change needed.

## Logging / secrets

Request-lifecycle logging (`app/main.py`) records method, path, status, duration, client IP — never request/response bodies, authorization headers, cookies, tokens, or query values. Structured logging sanitization redacts known-sensitive keys case-insensitively (`password`, `password_hash`, `access_token`, `refresh_token`, `token`, `authorization`, `jwt_secret_key`, `database_password`, `secret`, `api_key`, and more) in nested structures too. Every secret-bearing `Settings` field (`JWT_SECRET`, database password, provider API keys) uses `field(repr=False)` so it can never leak via an accidental `repr()`/log of the settings object itself. Confirmed during Phase 14 that no new code introduced in Phases 12/13 (Calendar OAuth tokens, Resend API key) logs a raw secret anywhere.

## Dead/debug surface (Phase 14, BUG-017)

Two debug-only routers (`/test/verify-token`, `/rbac/admin-only`) were mounted on the production app with no product purpose — removed. Neither was independently exploitable, but leaving unauthenticated-adjacent, no-product-purpose surface in a deployed API is exactly the class of thing a security pass should catch and remove, not rationalize as harmless.

## What's not covered yet

Real credentials for every external provider (Gemini/OpenAI, R2, Google Calendar, Resend) — every integration is behind an abstraction with a fake-provider test seam, but no real network call has been made from this environment (see `docs/ARCHITECTURE.md`). Branch protection / a live CI gate isn't configured yet (`docs/DEPLOYMENT.md`). No live penetration test or third-party audit has been performed — the findings above are from this codebase's own internal review, not an external assessment.
