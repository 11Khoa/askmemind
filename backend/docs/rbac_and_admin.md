# Roles, administration and audit

## Rollout and bootstrap

Deploy the backend on `feature/backend`, run `alembic upgrade head`, then deploy
the matching frontend. Migration `f61d09ea274b` sets every existing account to
`user`. Migration `a71c8d5e290f` creates the audit table. No account is promoted
automatically. On the server, deliberately promote one active existing account:

```sh
cd backend
python -m app.commands.admin bootstrap --email YOUR_EXISTING_ACCOUNT_EMAIL
```

The command refuses when an active admin already exists, serializes with other
role changes, and records a bootstrap event. It does not expose or change any
password. Afterwards, use Administration to create/manage other admins.

## Permissions

Public `POST /auth/register` accepts only email/password and always creates a
user. Extra fields (including role) are rejected with 422. Registration remains
controlled by `ENABLE_REGISTRATION`; administrator account creation is separate.

Users can upload, chat and inspect their own sources. They cannot delete any
document/chat or access `/admin/*`. Administrators can inspect and delete every
user's documents and chats. Administration access does not authorize adding
messages to another user's chat or running retrieval as that user. Normal
workspace lists/retrieval remain scoped to their current owner.

Every authenticated request loads active state, token version and role from the
database; a role in a client body or JWT is never authoritative. Changes to role
or active state increment token version and revoke all refresh sessions. Existing
sessions must sign in again. The last active admin cannot be disabled/demoted;
a PostgreSQL advisory lock serializes concurrent membership changes. Accounts
are disabled rather than deleted so owners and audit subjects stay identifiable.

## Administration API and UI

All `/admin/*` routes require admin permission. Lists return
`{items, total, page, page_size}` with page >= 1 and page_size 1..100.

* `GET /admin/users?q=`: users, searched by email.
* `POST /admin/users`: email, initial password, role (`user`/`admin`).
* `PATCH /admin/users/{id}`: role and/or is_active; unknown fields rejected.
* `GET /admin/documents?q=&user_id=`: documents with owner emails.
* `GET /admin/documents/{id}/chunks`: paginated extracted passages.
* `GET /admin/chats?q=&user_id=`: conversations with owner emails.
* `GET /admin/chats/{id}/messages`: paginated message content and citations.
* `GET /admin/activity?q=&user_id=`: recorded actions filtered by actor/target.

Existing document file/passage endpoints permit admin inspection across owners.
Existing DELETE endpoints require admin permission and preserve their cleanup,
worker-lock and retry behavior. Admin responses and source files use no-store.

The React `/admin` screen offers Users, Documents, Chats and Activity. Ordinary
workspace users have no delete/admin controls; this is additional UI behavior,
not the security boundary. Direct requests are denied at the server. Role/state
changes and destructive operations require confirmation. Bootstrap is server-only.

## Audit semantics and limits

User creation/role/state changes and successful resource deletion write business
audit events transactionally with the database change. Events retain actor ID,
target user ID, action, resource ID, result, request ID and time. They survive
resource deletion. Audit events have no update/delete endpoint.

Other requests (including login success/failure, uploads, processing retries,
questions, source inspection and administrative reads) are observed by ASGI
middleware after response completion. Stream generation failures are marked as
failures even though SSE uses HTTP 200. Failed anonymous logins have no known
actor. Middleware observation is best-effort: a write failure is logged but does
not undo an already completed request. It is not a tamper-proof external ledger.
Transactional privileged changes fail if their business audit cannot be written.

Request bodies, query strings, passwords, tokens, raw questions and PDF content
are not copied into audit metadata. Admins can separately inspect existing
documents/chats under their explicit permissions. There is no screen capture,
keystroke monitoring or historical reconstruction of pre-deployment activity.
Plan database retention/archival for activity as traffic grows; no automatic audit
purging is enabled by this change.
