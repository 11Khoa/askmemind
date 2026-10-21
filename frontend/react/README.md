# AskMeMind Web

React client for the AskMeMind document question-answering API.

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

The value must not end with a slash. The backend must allow the frontend
origin through its CORS configuration.

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

## Authentication

The client uses the access/refresh pair returned by `/auth/login`. Protected
requests (including streaming chat and document events) refresh once on `401`.
Concurrent requests share one refresh operation; rotated refresh tokens are
single-use. A failed refresh clears the session and requires signing in again.
Logout calls `/auth/logout` with the current pair before clearing the session.

Tokens are held only in memory, never in localStorage or sessionStorage.
Reloading the page requires signing in again. Persistent browser sessions would
require a backend change for Secure HttpOnly refresh cookies and CSRF protection.

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
and recovery payloads. Playwright tests use mocked backend responses and cover
login/logout and recovery on desktop/mobile. They do not send real reset emails.
