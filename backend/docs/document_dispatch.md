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
