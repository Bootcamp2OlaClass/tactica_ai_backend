# Database

PostgreSQL 16 + the `pgvector` extension (for `document_chunks.embedding`). Schema is managed entirely through Alembic — 21 migrations from `7236ba8655f4` (create initial tables) to `bf77af1169fd` (Phase 13, notification preferences/logs), one linear head, no branches outstanding. `alembic upgrade head` from an empty schema followed by `alembic check` is verified clean as of Phase 15.

## Ownership model

Every row that "belongs" to a student is reachable from `users.id` through one of two shapes:

1. **Direct**: `user_id` column, filtered directly (`semesters`, `conversations`, `document_chunks`, `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens`, `calendar_connections`, `notification_preferences`, `notification_logs`, `student_degree_progress`).
2. **Derived via a parent chain**: no `user_id` column of its own; ownership is proven by joining up to a `semesters.user_id` (or, for `documents`, up through `courses` to `semesters`). Repository queries filter on the *actual* parent chain read from the row itself, never a second client-supplied ID — this is the property the Phase 14 IDOR audit verified holds with zero exceptions across the whole schema (`courses`, `tasks`, `documents`, `extraction_candidates`, `roadmap_items` under `roadmap_weeks` under `semester_roadmaps`, `calendar_syncs` under `tasks`).

`document_chunks.user_id` is a deliberate **denormalization** — it's derivable via `documents -> courses -> semesters`, but Phase 07's tenant-isolation requirement made a direct, mandatory, non-nullable `user_id` column on the retrieval hot path worth the redundancy: RAG search is a single `WHERE user_id = :user_id ORDER BY embedding <=> :query_vector` query, not a multi-table join, on a code path where isolation correctness is the single most important property.

## Tables (24)

| Table | Introduced | Purpose |
|---|---|---|
| `users` | Phase 0 | Identity, `password_hash`, lockout counters, `deleted_at` (Phase 14 soft-delete). |
| `refresh_tokens` | Phase 2 | Hashed (never raw) refresh tokens; `family_id` for reuse-detection/revocation. |
| `password_reset_tokens`, `email_verification_tokens` | Phase 2 | Single-use, hashed, expiring tokens. |
| `semesters` | Phase 0 | Root of the academic-data ownership tree. Soft-delete (`deleted_at`). |
| `courses` | Phase 0 | Under a semester. Soft-delete. |
| `tasks` | Phase 0/9 | Under a course. Soft-delete. Extended in Phase 9 for roadmap/recovery-plan scheduling fields. |
| `documents` | Phase 3/5/6 | Under a course. No `user_id` of its own — ownership derives through `courses`. Processing-state machine fields (Phase 5), extraction fields (Phase 6). |
| `extraction_candidates` | Phase 6 | Review-gated LLM extraction proposals; accept -> real `Task`/`Course` field, reject -> discarded. Never auto-committed (ADR-006). |
| `document_chunks` | Phase 7 | `pgvector` embedding column; denormalized `user_id` (see above). No index yet (ADR-008 — deferred until real usage data justifies it). |
| `conversations`, `messages` | Phase 8 | AI Study Coach chat history. |
| `semester_roadmaps`, `roadmap_weeks`, `roadmap_items` | Phase 9 | `RoadmapItem.is_user_edited` (server-set only) protects manual edits from being overwritten by regeneration; `origin` (DETERMINISTIC/AI_GENERATED) keeps system facts visually/structurally distinguishable from AI suggestions. |
| `course_catalog_entries`, `prerequisites`, `degree_programs`, `degree_requirements`, `student_degree_progress` | Phase 11 | Degree Advisor. Populated with synthetic test-fixture data only in tests — no real catalog data exists in this environment (Phase 11 is `PARTIAL` for exactly this reason). |
| `calendar_connections`, `calendar_syncs` | Phase 12 | OAuth tokens (`access_token`/`refresh_token` encrypted at rest since Phase 14 — see `docs/SECURITY.md`); `calendar_syncs.provider_event_id` is the idempotency anchor (create only when null, else always update). |
| `notification_preferences`, `notification_logs` | Phase 13 | Opt-out preferences (no row = enabled); `notification_logs` is unique on `(user_id, notification_type, reference_id)` as a DB-level dedup backstop on top of the application-level check. |

## Soft-delete convention

`semesters`, `courses`, `tasks`, `documents` all use a `deleted_at` timestamp column, filtered out of every normal query rather than hard-deleted — consistent across every phase that touches them. `users.deleted_at` (Phase 14) follows the same shape but means something different: it's paired with PII anonymization (email/name overwritten) rather than a reversible soft-delete, since an account deletion is meant to be effectively permanent from the user's perspective. See `docs/SECURITY.md` for why a full hard-delete cascade wasn't implemented.

## Foreign-key delete behavior

Deliberately mixed, not uniform:
- Most parent-child relationships (`Semester -> Course -> Task`, `Document -> ExtractionCandidate`, etc.) use soft-delete at the application layer, so FK `ondelete` behavior rarely triggers in practice.
- `DocumentChunk`'s FK to `Document` is `RESTRICT`, not `CASCADE` — a deliberate Phase 07 choice to prevent silently losing embedded content as a side effect of an unrelated document-delete code path; deleting a document with chunks requires an explicit decision, not an implicit cascade.
- `CalendarConnection`/`CalendarSync`/`RefreshToken`/etc. use `CASCADE` on their `user_id`/`task_id` FK, since those rows have no independent meaning once their owner is gone.

This mix is why Phase 14's account-deletion feature is soft-delete + anonymization rather than a hard cascade delete: a correct hard delete across ~24 tables needs a per-table plan respecting exactly this mix, not a single blanket `DELETE FROM users WHERE id = ...` (which would fail outright on the first `RESTRICT` FK it hits).

## Migration verification procedure

Documented here because it tripped up local verification more than once this session: `tests/conftest.py`'s `db_session` fixture builds tables via `Base.metadata.create_all()`/`drop_all()` per test, **not** via Alembic. A test run leaves the schema empty but with no `alembic_version` table — running `alembic upgrade head` immediately after a test run (not before) is therefore the correct order, and is exactly what `.github/workflows/backend-ci.yml` does. Running migration checks against a database that pytest has already touched *without* first confirming it's in this post-drop_all state produces a false "everything is new" diff.
