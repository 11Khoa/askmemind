# AskMeMind Web

React client for the AskMeMind document question-answering API.

## Requirements

- Node.js 20.19 or newer
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
npm run build
npm run preview
```

The production build is written to `dist/`.
