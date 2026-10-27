# Processing progress and page checkpoints

Apply the additive database migration before starting the new API or workers:

```sh
docker compose build backend celery-worker
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d --no-deps backend celery-worker
```

Drain running tasks before replacing workers. Checkpoints are created by the new
worker; existing in-flight tasks and old ready documents do not retroactively
gain checkpoints. No new environment variables or external service is required.

`DocumentRead` and `document_status` SSE events now include optional
`processing_progress`. Its stages are `queued`, `extracting`, `ocr`, `chunking`,
`embedding`, `ready`, and `failed`. Page progress has `completed_pages`,
`total_pages`, `current_page`, and `reused_pages`; embedding progress has
`completed_chunks` and `total_chunks`. Stage counters describe the current stage,
not an estimated total duration. Empty/blank pages count as completed pages too.

Progress is committed to PostgreSQL before notifications. Clients can recover it
from list/detail responses after reconnecting, refreshing or switching devices.
SSE is best effort, throttled within a stage; if Redis fails, processing continues
and clients reconcile by polling. Attempt IDs and timestamps prevent stale
updates from undoing progress from a newer retry. Terminal events include the
last progress and a safe error code; raw provider error strings are not needed
for browser error messages.

Each completed native/OCR/blank page is committed to
`document_page_checkpoints`. A retry reuses only pages with a matching SHA-256
fingerprint of the complete PDF, model manifest, OCR enablement, DPI, pixel cap,
confidence threshold and extraction algorithm version. Changing those inputs
invalidates old page rows when extraction runs; changing timeouts or page/text limits does not erase
useful work. Limits are still enforced while reading cached pages. A failed page
is never cached. A timeout/retry starts a new time budget and can reuse completed
pages.

The existing complete chunk-set and embedding-batch checkpoints are preserved:
once chunking finished, retries go straight to unfinished embeddings. Page cache
fingerprinting is not rerun in that case: a retry resumes the already-built chunk
set, rather than applying new extraction/chunking settings. Upload a new copy to
intentionally rebuild that completed extraction with different settings. Page cache
text is private server-side data; it is not included in document/SSE responses.
It remains until document deletion, which cascades to its page rows. Budget for
this additional extracted-text storage when setting database retention/backups.
Incompatible models or code changes must bump the extraction fingerprint version.

Safe error codes include `ocr_timeout`, `ocr_page_limit`, `ocr_models`, `no_text`,
`file_missing`, `embedding_failed`, and `processing_failed`. Operators can still
inspect the existing stored `error_message` for detailed diagnosis. A failed
document retains completed page counts, allowing the UI to explain what a retry
will resume. Do not treat a Celery task return value as proof the document is ready;
the document's persisted status remains authoritative.

The React changes live on `feature/frontend-react`; deploy them after the backend
migration/update. The new UI also handles responses from an older backend without
progress fields, and the new backend remains usable by older clients.

## Administrator event stream

`GET /admin/documents/events` requires the same authenticated administrator role
as the admin list endpoints. It subscribes to a separate global Redis channel,
not a wildcard over private user channels. Only processing IDs, counters, status,
safe error codes and timestamps are fanned out; page text, file paths and raw
provider exceptions are excluded. The existing private user stream is unchanged.
Streams release their authentication database session, send heartbeats and close
after the configured bounded lifetime (240 seconds by default). Every reconnect
reauthenticates; role revocation is enforced on the next connection, rather than
claiming an already-open stream is revoked instantaneously.

The admin frontend connects only while the Documents tab is open, patches visible
rows in place, and reconciles a fresh snapshot on reconnect without changing the
current page, search or owner filter. Events outside the visible page trigger a
coalesced snapshot refresh, at most once every two seconds, to discover new rows.
No schema migration, additional service or environment variable is needed for
this SSE extension. Preserve `X-Accel-Buffering: no` and proxy streaming support.
