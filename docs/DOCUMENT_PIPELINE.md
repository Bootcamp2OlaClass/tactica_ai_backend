# Document Pipeline

A document's life, end to end: upload -> processing -> extraction -> review -> (optionally) embedding for retrieval.

## 1. Upload (`POST /api/v1/courses/{course_id}/documents`, Phase 03/05)

Multipart upload, PDF only, size-capped (`MAX_UPLOAD_SIZE`, default 10MB). Validated: MIME type, size, checksum, and path-traversal safety on the stored filename — this validation predates the Phase 14 security audit and was confirmed still solid rather than re-derived from scratch (see `docs/SECURITY.md`).

Storage goes through `StorageProvider` (ADR-004): `LocalStorageProvider` (dev default, live-verified) or `R2StorageProvider` (Cloudflare R2, contract-tested against a fake S3-compatible client — `NOT VERIFIED` against a real bucket, no credentials in this environment). Neither the router nor any service imports `boto3` or touches a filesystem path directly; everything goes through `save`/`load`/`delete` on the interface.

The document row is created and committed *before* enqueueing processing — the enqueue never races the row's own existence.

## 2. Processing (Celery task `documents.process_document`, Phase 05)

State machine on `Document.processing_status`: `QUEUED -> PROCESSING -> COMPLETED | FAILED`. An atomic claim (`UPDATE ... WHERE processing_status = 'QUEUED' RETURNING id`) prevents two workers from double-processing the same document if a task is redelivered.

- **Native PDF text extraction**: `pdfplumber` (MIT-licensed, chosen over PyMuPDF's AGPL license) — page-by-page text, with a page-provenance JSON artifact stored alongside the extracted text (needed later so extraction candidates and chat citations can point at a specific page range).
- **OCR-required detection**: real and tested — a scanned/image-only PDF is correctly identified as such.
- **OCR execution is not implemented.** No Tesseract runtime or cloud OCR credential exists in this environment. A scanned PDF reliably reaches `FAILED` with `extraction_method=UNSUPPORTED`, honestly, rather than pretending to extract text that isn't there. `ExtractionMethod.OCR` is reserved in the enum for when this becomes available.

`POST /api/v1/documents/{id}/reprocess` re-enqueues from scratch (`202 Accepted`).

**Infrastructure note**: this pipeline requires a Celery worker subscribed to the `documents` queue running alongside the API — the worker's `-Q` flag must list it explicitly (Phase 05's BUG-015 was exactly this: the worker only consumed the default queue, and an uploaded document sat in `QUEUED` forever with no error, because nothing was subscribed to receive it). `docker compose up` brings up `backend`, `worker`, `beat`, `redis`, and `db` together; running the API alone (`uvicorn app.main:app`) with no worker means uploads will queue but never process.

## 3. Structured extraction (Celery task `ai.extract_document`, Phase 06)

One `LLMProvider.extract_structured` call per document against `AcademicDocumentExtraction` (course metadata, tasks/deadlines, exams, grading-policy text) — see `docs/AI_RAG_ARCHITECTURE.md` for the provider/schema-enforcement details and the document-injection mitigation in the system prompt.

Every extracted fact becomes an `ExtractionCandidate` row, **never auto-committed** (ADR-006) — ai output is a proposal, not a fact, until a human accepts it.

- `POST /api/v1/extraction-candidates/{id}/accept` — creates a real `Task`, or fills a `Course` field only if it was previously blank (never silently overwrites a manually-entered value — manual data always wins).
- `POST /api/v1/extraction-candidates/{id}/reject` — discarded, no side effect.

`IMPORTANT_DATE`/`GRADING_POLICY` candidate types have no accept-side persistence target yet (`Course` has no grading-policy field) — accepting one only records the review decision, deliberately, not a bug.

**No frontend Review UI exists yet.** The backend accept/reject API is complete and tested; nothing in the frontend currently lists a document's candidates for a student to review. A tracked, known gap, not an oversight.

## 4. Embedding for retrieval (Celery task `ai.embed_document`, Phase 07 — separate, opt-in step)

`POST /api/v1/documents/{id}/embed` triggers fixed-size chunking (with page-range tracking) + `EmbeddingProvider` calls, producing `document_chunks` rows (`pgvector`, tenant-scoped via a mandatory `user_id`). This is what powers RAG retrieval for the AI Study Coach — see `docs/AI_RAG_ARCHITECTURE.md`. Not automatically triggered by upload/extraction; a document can be uploaded and its tasks extracted without ever being embedded for chat.

## Failure isolation

Every step in this pipeline is independently retryable and independently failable — a document stuck at `FAILED` in processing doesn't block extraction from being retried once fixed (via reprocess), and a document that was never embedded doesn't block its tasks from having already been extracted and accepted. No step assumes a previous step's success beyond what it structurally requires (extraction needs `COMPLETED` processing; embedding needs the same).
