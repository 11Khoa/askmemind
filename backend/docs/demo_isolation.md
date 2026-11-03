# Browser demo account isolation

## Schema and scope

`users.is_demo`, `demo_retention_minutes` (15–1440, default 60), and
`demo_upload_enabled` (default true) are account settings. They live on User
because the existing admin and authentication flows already read this row. A
check constraint forbids shared demo administrator accounts.

`demo_sessions` owns an unguessable server-generated UUID, user ID, immutable
creation/expiry times and notice acceptance/version. `documents.demo_session_id`
and `chats.demo_session_id` are nullable indexed cascading foreign keys. Existing
rows stay NULL. Chunks, vectors, extraction checkpoints and messages remain under
their existing aggregate roots and cascading FKs.

HTTP repositories receive `DataScope` from an authenticated dependency. Demo
reads match both account and session. Normal reads exclude demo roots and retain
the existing service-level ownership checks and 403 behavior; cross-session demo
IDs return 404. Admin RBAC continues to allow inspection across accounts.
Retrieval joins the same document scope for both vector and full-text search.
Explicit document IDs in questions are authorized before provider calls. Private
SSE publications use a separate channel per demo session, never the shared
account channel; the authorized global admin stream retains metadata only.

## Authentication and API

A successful browser `/auth/login` creates a session for demo accounts and sets
`askmemind_demo`, a domain-separated HMAC-signed UUID in a host-only HttpOnly cookie with Path=/ and the existing refresh
cookie Secure/SameSite policy. Production settings require Secure. Native JSON
token clients do not bypass the session requirement; demo use is a browser flow.
Refresh does not create or extend the demo session. Browser tabs share a session
cookie; independent browsers/cookie jars receive independent sessions.

- `GET /demo/status`: configuration, current expiry and notice acceptance, no ID.
  Normal accounts return `is_demo=false` without creating a session. Missing,
  revoked or expired demo cookies return 410.
- `POST /demo/bootstrap`: keep an active current session, or create a new one
  after expiry/deletion. This never renews an active session's deadline.
- `POST /demo/notice/accept`: JSON `{ "notice_version": "v1" }`; rejects a stale
  version with 428, then records the current version and acceptance timestamp.
- `DELETE /demo/session`: no identifier in URL/body; selects only the authenticated
  cookie's own session (including an expired session awaiting cleanup), deletes
  it and clears the cookie. Response: `deleted`, `requires_bootstrap`.
- `PATCH /admin/users/{user_id}/demo-config`: full JSON with `is_demo`,
  `demo_retention_minutes`, `demo_upload_enabled`. Admin-only, validates ranges.
- `GET /admin/users/{user_id}/demo-sessions`: admin-only paginated session metadata.
- `DELETE /admin/users/{user_id}/demo-sessions/{session_id}`: admin-only targeted
  cleanup, checks the account/session pair and never logs the cookie identifier.
- `DELETE /admin/users/{user_id}/demo-data`: admin-only deletion of all demo
  sessions belonging to that account, preserving normal legacy rows.

Every demo mutation checks the existing exact Origin plus
`X-CSRF-Protection: 1` policy. Upload, retry, chat creation, raw messages and both
question routes reject unaccepted/outdated notice versions with 428. Expiry is
fixed at session creation; updated retention affects future sessions only.
Upload permissions and notice versions are rechecked on every protected action.
All responses with source/session data are no-store.

Turning demo mode on/off invalidates existing access/refresh sessions. Legacy
normal data is hidden while demo mode is on, never assigned to a browser session.
Turning demo mode off requires zero remaining demo sessions: delete demo data
first. Previously retained normal rows then remain available to their normal
owner. Demo accounts must be taken out of demo mode before granting admin role.

## Cleanup and worker races

One `cleanup_session` implementation serves self-delete, admin delete and the
`demo.cleanup` task. It locks the session, expires it and invalidates document
attempts, then commits revocation **before** file removal. It reacquires the
session lock, unlinks PDFs (missing files are fine), deletes document/chat roots
with DB cascades, and deletes the session transactionally. File failures leave
an expired session and records available for retry. A crash after unlink is safe:
the next run sees a missing file and completes DB cleanup. Audit metadata contains
actor/account IDs and deletion counts, never session cookies or source content.
An already completed identifier is a no-op.

Workers check session validity before constructing a processing service, during
OCR polling/page checkpoints, before chunk/vector writes and before completion.
Persist operations lock the session before aggregate rows; cleanup uses the same
order. No session lock is held during OCR or provider requests. A late provider
result is discarded after revocation; queued stale document jobs exit without
retry. Chat final persistence uses the same guard. Private SSE streams also end
by their original session deadline. The server cannot retract data already sent
to a browser or stop a provider request already in flight.

Celery Beat enqueues cleanup every 300 seconds, processing at most 100 expired
sessions per sweep. Requests and workers reject expired sessions immediately;
physical deletion is eventual, normally on the next sweep plus queue delay.
Run **one** Beat scheduler. Monitor worker/Beat health and `demo.cleanup.*` logs;
there is no guarantee of physical deletion on schedule while these are down or
disk permissions prevent deletion. Failed cleanup is retried on later sweeps.
Provider retention is independent of AskMeMind retention. This feature does not
implement provider deletion, backup retention or a legal compliance guarantee.

## Quotas

Defaults (no new mandatory env):

| Env | Default |
| --- | --- |
| `DEMO_NOTICE_VERSION` | `v1` |
| `DEMO_MAX_FILES` | 5 per session |
| `DEMO_MAX_UPLOAD_SIZE_MB` | 10, also bounded by normal upload limit |
| `DEMO_QUESTIONS_PER_MINUTE` | 10 per session |
| `DEMO_MAX_SESSIONS_PER_ACCOUNT` | 100 including expired sessions not yet cleaned |

Existing account-wide upload/question limits remain as additional abuse limits.
Document count and storage quotas remain bounded across the account, including legacy documents.
There is intentionally no billing system or automatic account creation. Notice
version changes require acceptance again without extending the expiry.

## Frontend

Admin searches existing Users by email; mutations use the returned user UUID.
Demo settings and full-account deletion have separate explicit controls and
confirmation. The workspace gates actions with the Vietnamese notice, shows the
actual retention and expiry, and offers session-only self-delete. It stores no
session ID in browser storage. There is no existing Privacy Policy page to link.

Deletion/expiry unmounts Workspace: React state, selected documents/chats,
citations, PDF viewer and streams are disposed. Failed cleanup blocks workspace
access and offers retry. A successful delete shows a fresh-session action, not
old cached data. Same-browser tabs receive an identifier-free BroadcastChannel
reset; server-side scope enforcement remains authoritative when unavailable.

## Deployment and rollback

Deploy migration **before** new API/workers, and deploy frontend afterward:

```bash
docker compose build backend celery-worker celery-beat
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d --no-deps backend celery-worker celery-beat
```

Existing deployments must already configure `AUTH_CSRF_TRUSTED_ORIGINS`, cookie
Secure/SameSite and credentialed CORS as required by browser authentication. Beat
uses the same broker; cleanup runs in the worker with the existing upload volume.
Do not scale Beat to multiple schedulers. No new public ports are needed.

Migration: `c91d2a304ef6` after `b84e1c720ad3`. Upgrade is additive. Before any
schema downgrade, stop traffic/workers, delete all demo sessions through the
cleanup service so files are removed, then downgrade. Downgrade removes scope
columns and must not be used to convert uncleaned demo rows into normal data.
Always retain DB/upload backups under your own retention policy.
