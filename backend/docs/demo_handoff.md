# Demo isolation handoff

No new commits or pushes were made. Backend changes are uncommitted on
`feature/backend` in `/workspace/askmemind`. Frontend changes are uncommitted on
`feature/frontend-react` in `/workspace/askmemind-frontend-demo`, based on the
latest remote `3434b2c`. This separate checkout keeps both branch scopes intact
without temporary commits. Local review patches are also saved at
`/workspace/askmemind-demo-backend.patch` and
`/workspace/askmemind-demo-frontend.patch` (include new files, no models/secrets).

See [implementation and deployment](demo_isolation.md).

## Verification

- Full backend suite: **465 passed**, including 22 new demo tests.
- Frontend TypeScript + Vite production build: passed.
- Frontend ESLint: passed.
- Frontend unit tests: **43 passed**.
- Entire Playwright suite: **68 passed** across desktop/mobile.
- Demo screenshot/browser scenarios rerun: **8 passed**.
- Migration downgrade to `b84e1c720ad3` and upgrade to `c91d2a304ef6`: passed on local test PostgreSQL.
- Compose schema parsing, Python compileall and Git diff whitespace checks: passed.
  The local checkout has no `POSTGRES_*` Compose values; PostgreSQL/Redis tests
  used the existing local test containers, not this production Compose stack.
- `alembic check` reports only two **pre-existing** unmanaged expression indexes:
  `ix_chunks_content_fts` and `ix_users_email_lower_unique`. Reproduced unchanged
  using an archived, unmodified backend HEAD against the previous migration.
  This was not altered because it is unrelated to demo isolation.
- Vite retains the pre-existing >500 kB chunk warning (current JS about 515 kB,
  158 kB gzip). Backend retains existing PyMuPDF/TestClient/fork warnings.

Verification uses the local cloud PostgreSQL/Redis and stubbed external provider
responses. A real second database connection deletes a demo session while a
worker's embedding call is suspended; the late result cannot resurrect rows.
Other tests cover both vector and full-text scopes, child repository reads, real
Redis cross-session fanout, signed-cookie tampering, CSRF, quotas, audit, legacy
rows and self-delete preserving a second browser's files/messages.
No deployment, production load test or provider retention verification was done.

## Backend files

- `.env.example`
- `backend/alembic/versions/c91d2a304ef6_demo_isolation.py`
- `backend/app/core/celery_app.py`
- `backend/app/core/config.py`
- `backend/app/core/data_scope.py`
- `backend/app/core/demo_dependencies.py`
- `backend/app/core/dependencies.py`
- `backend/app/core/rate_limits.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/chat.py`
- `backend/app/models/demo_session.py`
- `backend/app/models/document.py`
- `backend/app/models/user.py`
- `backend/app/repositories/chat_repository.py`
- `backend/app/repositories/chunk_repository.py`
- `backend/app/repositories/document_repository.py`
- `backend/app/routers/admin.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/chat.py`
- `backend/app/routers/demo.py`
- `backend/app/routers/document.py`
- `backend/app/routers/upload.py`
- `backend/app/schemas/user.py`
- `backend/app/services/admin_service.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/demo_service.py`
- `backend/app/services/document_events.py`
- `backend/app/services/document_progress.py`
- `backend/app/tasks/demo_cleanup.py`
- `backend/docs/demo_isolation.md`
- `backend/tests/test_demo_isolation.py`
- `docker-compose.yml`

- `backend/docs/demo_handoff.md` (this file)

## Frontend files (separate checkout)

- `frontend/react/README.md`
- `frontend/react/e2e/admin-routing.spec.ts`
- `frontend/react/e2e/demo.spec.ts`
- `frontend/react/src/lib/admin.ts`
- `frontend/react/src/lib/demo.ts`
- `frontend/react/src/lib/http.ts`
- `frontend/react/src/lib/types.ts`
- `frontend/react/src/workspace/AdminPanel.tsx`
- `frontend/react/src/workspace/AppRoot.tsx`
- `frontend/react/src/workspace/Workspace.tsx`
- `frontend/react/src/workspace/components/DemoAccountDialog.tsx`
- `frontend/react/src/workspace/components/DemoWorkspace.tsx`
- `frontend/react/src/workspace/components/DocumentsPanel.tsx`
- `frontend/react/src/workspace/components/demo.css`
- `frontend/react/src/workspace/components/demoContext.ts`
