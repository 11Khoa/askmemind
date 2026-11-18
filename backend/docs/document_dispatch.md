# Durable document dispatch

Migration `e24a7019bc65` adds a document_jobs intent committed atomically with
upload/retry. Existing processing attempts are seeded. The synchronous publish
is an optimization; a broker outage now returns 202 with a queued document, not a
failed upload that invites duplicate submissions. Beat dispatches pending rows
every 30s. Keep one Beat and a maintenance consumer running.

After 600s without checkpoint progress (also at least twice page timeout), the
same token is dispatched again. Advisory processing locks and attempt guards
prevent duplicate writes. A recent checkpoint postpones recovery. After ten
successful stale deliveries without progress, mark that attempt failed for a
manual retry; broker outages do not consume this budget. Closed/superseded
intents are purged; document/session deletion cascades intents.

No PostgreSQL transaction spans the broker call. A publish acknowledgment lost
in transit may duplicate delivery; it cannot provide exactly-once transport.
Queued tasks always reauthorize against the current document/session state.

SQL commit acknowledgment can be ambiguous. Upload SQL errors retain the PDF
rather than delete a potentially committed document's file. An orphan file sweep
is needed for genuinely absent rows. A broker or dispatcher failure never clears
saved pages/chunks. Deploy the migration before API/workers/Beat.

## Queue isolation and deadlines

New processing uses `documents`; cleanup, dispatch and password reset use
`maintenance`. Compose adds `celery-maintenance` with concurrency 1 and the same
upload volume. The processing worker also drains legacy `celery` messages during
rollout. Start maintenance before routing new tasks, and retain Beat for recovery.
Default document concurrency is now 1 for the small VPS. Increase only after load
measurement. An OCR burst cannot consume the maintenance worker's slot.

`DOCUMENT_TASK_TIME_LIMIT_SECONDS` defaults to 3600; soft limit is 30s earlier,
Redis visibility is 600s later. Native page/document guards normally stop work
sooner. Hard kills still rely on attempt guards/outbox/late acknowledgment for
recovery; this does not make provider calls exactly once.
