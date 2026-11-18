# Hardening rollout — 18 November 2026

Backend changes are on `feature/backend`; React changes are on
`feature/frontend-react`. Each fix has its own commit. Neither branch was pushed.

## Deployment

Back up PostgreSQL and the upload directory using the existing deployment
procedure. This release adds migration `e24a7019bc65` (durable document dispatch
intents), and the `celery-maintenance` service. Use matching backend and React
revisions; build React from its branch, since this repository's backend branch
contains an older frontend snapshot.

Example backend rollout from the backend checkout:

```sh
docker compose build backend celery-worker celery-maintenance celery-beat
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d --no-deps celery-maintenance celery-worker celery-beat backend
docker compose exec backend python -m app.commands.check_pdf_ocr
```

Do not interrupt active ingestion merely to deploy; drain/pause uploads and wait
for active jobs, or plan for checkpoint recovery. Run only one Beat scheduler.
The maintenance worker is required for retention, email, outbox recovery and
orphan cleanup. See `document_dispatch.md` for delivery semantics and timeouts.

The API port now binds to host loopback. A host Nginx can continue using
`127.0.0.1:8000`; an independently containerized proxy must use a shared private
network, not the host's loopback. Verify the actual proxy route before rollout.
Set explicit trusted proxy addresses as described in `proxy_boundary.md`.

Production now rejects weak signing keys. Keep an existing sufficiently strong
key; if it is weak, replacing it invalidates existing signed sessions/tokens.
Generate a random secret locally, never reuse example/test values.

New optional settings and their defaults are in `.env.example`. Defaults bound
OCR concurrency to one processing worker and separate lightweight maintenance
work. Native PDF limits are additional virtual-memory headroom, not a promise
about total container RSS. Keep VPS/container resource budgets based on actual
measurements. Redis concurrency leases cap generation and SSE across API
processes; generation leases expire after 900 seconds and streams after 300.
An abnormal generation exceeding its lease could overlap a later request; a
strict provider-wide wall-clock deadline/lease renewal remains follow-up work.

## What this batch fixes

- Question content removed from retrieval summary logs.
- Weak production signing keys rejected; public API bind restricted.
- Native PDF parsing moved out of the parent process, with deadlines, CPU and
  address-space limits, and credential-free child environments.
- Upload processing intents committed with documents; broker outages no longer
  silently strand uploads. Beat retries stale intents, with attempt guards.
- Cleanup/email/outbox work isolated from OCR, with bounded task runtime.
- Redis-backed global, account and demo-session concurrency admission.
- Atomic upload-file publication; conservative cleanup of stale orphan uploads.
- Remote document membership reconciliation, including deletions after reconnect.
- Question submission locked before asynchronous demo consent checks.
- Incomplete answer streams rejected when the required final event is missing.
- Completion notices recovered from document snapshots.
- Authenticated workspace retained on transient refresh outage, with explicit
  authentication rejection still clearing the session.
- Obsolete Streamlit sources removed on both branches.
- React build, lint, unit and desktop/mobile browser checks added to CI.

## Remaining review work

This batch does not close every item in the architecture review. In particular:

- Total conversation/message quotas, pagination and broader storage accounting.
- Strict generation deadlines, provider connection pooling and bounded retries.
- Mandatory owner scope in all repository operations and transaction/UoW cleanup.
- Retrieval compatibility filters for embedding versions, representative
  multi-document evaluation, calibrated confidence, claim-level citation checks,
  and the policy for streaming content before final verification.
- Vector indexing must be selected against the actual embedding dimensions and
  measured workload; no unverified ANN index was added.
- Python dependency locking/CVE audit, frontend tooling advisories, coordinated
  cross-branch release verification and schema drift checks.
- Non-root container rollout with correct bind-mount ownership; parser children
  have reduced environment/resource access but are not a filesystem/network
  security sandbox.
- Readiness/metrics, cleanup heartbeat alerts, token/audit retention, backup
  restore drills, browser header policy and admin step-up authentication.
- IME/upload-limit consistency, lazy bundles and workspace state decomposition.
- Actual VPS load, broker/process fault and external proxy/firewall verification.

No live VPS or provider requests were used for this batch's verification.
