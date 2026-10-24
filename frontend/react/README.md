# AskMeMind Web

React client for the AskMeMind document question-answering API.

## Document retry

Failed documents show a Retry action on their own row. It sends a bearer-authenticated
`POST /documents/{id}/retry` without a body, expects `202` with DocumentRead and
updates the existing row instead of uploading a duplicate. A failed request keeps
the error visible and reconciles the document with `GET /documents/{id}`.

`GET /documents/events` pushes processing results; events carry `document_id`,
`status`, `page_count`, `error_message`, `processing_attempt_id` and `updated_at`.
The client discards stale events and also polls every 2 seconds while processing
because Redis Pub/Sub cannot replay messages missed during disconnects. Retry
and upload controls are independent, and repeated clicks are blocked per document.
The matching backend migration must be applied before starting the new API/worker.

## Requirements

- Node.js 24 LTS (used for builds and tests)
- The FastAPI backend running on port 8000

## Local development

```bash
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies requests under `/api` to
`http://127.0.0.1:8000`.

## Environment

Copy `.env.example` to `.env.local` only when the API is served from a
different origin:

```env
VITE_API_URL=https://api.example.com
```

The value must not end with a slash. Cross-origin deployments must allow the
exact frontend origin, credentials and `X-CSRF-Protection` in backend CORS.

## Commands

```bash
npm run dev
npm run lint
npm test
npx playwright install chromium
npm run test:e2e
npm run build
npm run preview
```

The production build is written to `dist/`.

## Live document updates

Document SSE reconnects automatically after network errors, normal proxy closure
or a 45-second heartbeat silence, with jittered backoff capped at 30 seconds. It
rotates at four minutes to recheck the session through the authenticated client.
Each connection reconciles document metadata; processing documents also retain
their polling fallback. Transient background failures show a quiet reconnecting
label instead of a global Network error. Leaving the workspace cancels the stream
and pending retries. Question generation is never automatically resubmitted.

Deploy the matching `feature/backend` stream lifecycle changes too. For VPS
reverse proxies, see `backend/docs/sse_recovery.md` and the updated Nginx example
on that branch; code changes do not automatically reload your VPS Nginx config.

## Vercel deployment

Set the Vercel project's Root Directory to `frontend/react` and select the
branch containing the frontend changes for deployment. The `vercel.json` in
that directory selects Vite, builds with `npm run build`, publishes `dist`,
and serves the React entry page for `/reset-password`, `/admin` and their
trailing-slash variants. These explicit rewrites are required for direct visits,
reloads and authentication redirects; Vite's development fallback does not
validate the deployed hosting rules. Missing `/api/*` paths are not rewritten.

Set `VITE_API_URL` to the deployed backend origin in Vercel environment
variables, then redeploy. Vite's local `/api` proxy is only used during local
development. Allow the frontend origin in backend CORS settings.

Configure `PASSWORD_RESET_URL` in the API and worker to
`https://your-frontend.example/reset-password`. Verify `/`,
`/admin`, `/admin/` and `/reset-password` on the deployed site; the latter shows an incomplete-link
message when opened without a token.

Run `VITE_API_URL=/api npm run test:e2e:production` to test the built SPA with a
static test host that applies only the rewrites declared in `vercel.json`.
It covers direct admin visits/reloads, sign-out/sign-in and browser history.
Authentication APIs are mocked; this does not deploy or modify the live site.

## Authentication

The browser client expects the cookie-based backend contract below. It cannot
persist a session with the old JSON-only refresh-token API. No backend changes
are included in this frontend worktree change.

Access tokens stay in memory. Refresh tokens are managed exclusively by the
browser through an HttpOnly cookie; React never reads or stores them. Old
AskMeMind token keys in localStorage/sessionStorage are removed on startup.

Every API request uses `credentials: 'include'`. Before loading protected data,
the app calls `/auth/refresh` once to restore the session. A `401` without a
valid cookie opens sign-in normally. Other startup failures display an error
and allow retrying restoration. Protected requests, including chat/document
streams, refresh once on `401` and retry once with the new access token.

Concurrent requests share a refresh promise. Web Locks serialize login,
refresh and logout across tabs on the same frontend origin in supported
HTTPS/localhost browsers. BroadcastChannel propagates sign-in/sign-out without
sharing any tokens. Cookie persistence across tab/browser restarts depends on
the backend setting Max-Age/Expires and the browser allowing that cookie.

## Browser auth API contract

All paths below are relative to `VITE_API_URL` (default `/api`):

| Request | Body | Successful response |
| --- | --- | --- |
| `POST /auth/login` | `{ "email": "...", "password": "..." }` | `200`, `{ "access_token": "...", "token_type": "bearer" }`, Set-Cookie |
| `POST /auth/refresh` | No body | `200`, same access-token JSON, rotated Set-Cookie |
| `POST /auth/logout` | No body; bearer access token in Authorization | `204`, revoke refresh/access tokens and clear cookie |

The frontend sends `X-CSRF-Protection: 1` on these three requests. The backend
must validate trusted Origin values and require appropriate CSRF protection;
the header alone does not implement server-side protection. CORS must permit
this header and credentials for explicit frontend origins. The browser sets
Origin and Cookie automatically; React does not set either header.

The backend must use HttpOnly and Secure in production, with SameSite suitable
for the deployment and a persistent cookie lifetime bounded by the refresh
session's absolute expiry. Cookie Path must cover these requests: `Path=/`
works for both direct API origins and the local `/api` proxy. A cookie scoped
only to `/auth` will not be sent to the browser-visible `/api/auth` paths.
Cookie deletion must use the same name, path and domain as cookie creation.
Never return the browser refresh token in JSON or log Cookie/Set-Cookie values.

Prefer same-site custom domains (for example `app.example.com` and
`api.example.com`) or a same-origin API proxy. A `vercel.app` frontend calling
an unrelated API domain may be blocked by third-party cookie restrictions even
with credentials included. SameSite=None requires Secure but does not override
browser third-party cookie blocking. The local Vite proxy is not a production
proxy; deployment/domain configuration must provide that separately.

Password recovery uses `/auth/forgot-password` and `/auth/reset-password`.
Configure `PASSWORD_RESET_URL=http://localhost:5173/reset-password` in both the
API and Celery worker for local development. Use the actual frontend origin
with HTTPS in production, and configure SMTP as described in
`../../backend/docs/authentication.md`.

The reset page consumes `#token=...` and removes the fragment before mounting
analytics. Configure the production host to serve `index.html` for
`/reset-password` as well as `/`. Reset success returns the user to sign-in;
it does not create a new session.

Unit tests cover token rotation, concurrent requests, refresh failures, logout
and recovery payloads. Playwright uses mocked backend responses that set real
HttpOnly cookies in Chromium to cover reload/reopening, multi-tab rotation,
logout, blocked storage and recovery on desktop/mobile. These tests do not
validate the backend's cookie/CSRF implementation or send real reset emails.
# Document management and source inspection

This client supports document/conversation deletion with confirmation, source
passages, and authenticated PDFs opened at their cited page. It requires the
matching `feature/backend` API changes: `DELETE /documents/{id}`, `DELETE
/chats/{id}`, `GET /documents/{id}/chunks/{chunk_id}`, and `GET
/documents/{id}/file`. Deploy that backend first.

Deleting a document removes its original PDF, chunks/vectors and cached source
excerpts; saved answer text remains until its conversation is deleted. A cleanup
failure can leave a `deleting` document: use its delete action again to finish.
The source dialog uses a temporary blob URL, never a token in the URL. Native
PDF page navigation depends on browser support; an open-in-new-tab link is also
provided. Follow-up context is loaded on the server without extra client payloads.

## Roles and administration

Ordinary users can upload/chat/read their own sources, but cannot delete resources.
Only admins see destructive controls and the Administration navigation item.
The `/admin` screen verifies `/auth/me` before rendering role controls and uses
server-protected `/admin/*` endpoints. It provides paginated Users, Documents,
Chats and Activity views, filters, role selection when creating accounts, account
enable/disable, confirmed role changes, and inspection/deletion across owners.

Role/account-state changes invalidate existing server sessions. Attempts to remove
the last active admin display the server's refusal. No client-selected role is
sent by public sign-up. Passwords exist only in the creation form until submission
or close; they are not stored in browser storage or activity metadata.

Deploy the backend and apply its role/audit migrations first. All existing
accounts initially become users; bootstrap the first admin explicitly with the
server command documented in `backend/docs/rbac_and_admin.md` on `feature/backend`.
Configure SPA hosting to serve `index.html` for `/admin` as well as the existing
reset-password route. No production account is automatically elevated by the UI.
