# AskMeMind

**Citation-aware question answering over your PDFs, built as a production-minded RAG system.**

[![CI](https://github.com/11Khoa/askmemind/actions/workflows/ci.yml/badge.svg)](https://github.com/11Khoa/askmemind/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791)
![React](https://img.shields.io/badge/React-19-61dafb)

<img width="881" height="554" alt="AskMeMind screenshot" src="https://github.com/user-attachments/assets/17b2fa5c-f525-4fd0-90fb-698a643ce36c" />

> **Live demo:** https://askmemind.fullfact.xyz
> <!-- Add a short GIF here: upload PDF -> status turns ready -> streamed answer with citations -->

AskMeMind lets users upload PDFs and ask questions in English or Vietnamese. Every answer is grounded in retrieved passages and links back to the exact page it came from. When the evidence is weak, the system says it does not know instead of guessing.

The project focuses on the parts of RAG that usually decide whether it works outside a demo: **measured retrieval quality, guardrails against hallucination, asynchronous ingestion, real-time status updates, and observability.**

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [How a Question Is Answered](#how-a-question-is-answered)
- [Evaluation](#evaluation)
- [Tech Stack](#tech-stack)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development](#local-development)
- [Configuration](#configuration)
- [API Overview](#api-overview)
- [Testing](#testing)
- [Deployment](#deployment)
- [Reliability and Observability](#reliability-and-observability)
- [Security](#security)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Project Structure](#project-structure)

---

## Features

**Retrieval and answering**
- Page-aware PDF extraction (PyMuPDF) with chunks that keep page and character offsets, so citations are traceable.
- Local CPU OCR fallback for scanned PDF pages using RapidOCR + ONNX Runtime (Vietnamese/English). See [setup, limits and rollout](backend/docs/pdf_ocr.md).
- Resumable per-page extraction checkpoints and persisted live processing progress. See [migration and retry behavior](backend/docs/document_progress.md).
- Three retrieval strategies: pgvector similarity, PostgreSQL full-text search (GIN index), and **hybrid search using weighted Reciprocal Rank Fusion (RRF)**.
- Optional heuristic reranker over a larger candidate pool.
- Optional bounded retrieval retry: when evidence is weak, the query is rewritten into keywords and retried (capped number of attempts, no extra LLM call).
- Streaming answers over Server-Sent Events (SSE).

**Reliability and safety**
- Confidence guardrail: low-evidence questions return a stable "I do not know" response without calling the LLM.
- Citation validation: answers must cite `[Source N]` markers that exist in the built context.
- Prompt-injection isolation: document text is delimited as untrusted data in the generation prompt.
- Per-user data isolation on every retrieval query.

**Platform**
- JWT authentication, size and signature-checked PDF uploads.
- User/admin roles, admin-only deletion, and an audited administration API for users, documents and conversations.
- Asynchronous document processing with Celery and Redis; document status is pushed to the browser in real time via Redis pub/sub and SSE.
- Chat history with persisted citation metadata.
- Delete conversations or documents, including PDF/chunk/vector cleanup. Inspect source passages and authenticated original PDFs.
- Bounded conversation context for follow-up questions, isolated by the selected document scope and grounded in newly retrieved evidence.
- Structured JSON logs with request IDs, stage latency and token usage; liveness and readiness probes.
- Alembic migrations, Docker Compose stack, GitHub Actions CI against a real pgvector database.
- React client (Vite, TypeScript, i18n) and a lightweight Streamlit client.

---

## Architecture

```mermaid
flowchart LR
    U[React client] -->|HTTPS| N[Nginx]
    N --> API[FastAPI]
    API --> PG[(PostgreSQL + pgvector)]
    API -->|enqueue| R[(Redis)]
    R --> W[Celery worker]
    W -->|extract, chunk| PG
    W -->|embed passages| NV[NVIDIA NIM embeddings]
    W -->|publish status| R
    R -->|pub/sub| API
    API -->|SSE: document status| U
    API -->|embed query| NV
    API -->|generate answer| G[Groq LLM]
    API -->|SSE: answer tokens| U
```

The backend is layered so that external providers can be swapped without touching business rules:

| Layer | Responsibility |
|---|---|
| **Routers** | HTTP input and output, validation boundaries, status codes |
| **Services** | Business rules, RAG orchestration, guardrails |
| **Repositories** | All SQLAlchemy and SQL access |
| **Providers** | External AI APIs (NVIDIA embeddings, Groq chat) behind small interfaces |

---

## How a Question Is Answered

```mermaid
flowchart TD
    Q[Question] --> R1[Retrieve: vector + full-text]
    R1 --> F[Weighted RRF fusion]
    F --> A{Evidence strong enough?}
    A -- no, retries left --> RW[Rewrite query to keywords] --> R1
    A -- no --> NA[Return 'I do not know']
    A -- yes --> RR[Optional heuristic rerank]
    RR --> CB[Build citation-aware context]
    CB --> LLM[Grounded LLM answer]
    LLM --> V{Citations valid?}
    V -- no --> NA
    V -- yes --> OUT[Answer + page citations]
```

- **Why RRF:** vector distances and full-text ranks live on different scales. Fusing by rank position avoids normalizing incompatible scores.
- **Why a deterministic rewriter:** the retry step strips stop words (English and Vietnamese) instead of calling another model, which keeps it cheap, predictable, and easy to test.
- **Reranker:** a transparent scoring function (keyword overlap, original rank, phrase match), not a cross-encoder. It is off by default and meant to be compared against a model-based reranker later.

---

## Evaluation

Retrieval quality is measured, not assumed. The runner compares methods on a bilingual dataset and writes JSON, CSV and Markdown reports.

```bash
cd backend
python -m evaluation.run_evaluation                      # all methods
python -m evaluation.run_evaluation --methods vector hybrid --top-k 5
python -m evaluation.run_evaluation --with-answers       # also calls the LLM
```

Available methods: `vector`, `fts_search`, `hybrid`, `hybrid_reranked`. Reports are written to `backend/evaluation/reports/`.

**Latest benchmark** (18 questions, 9 English and 9 Vietnamese, K = 5):

| Method | Hit@5 | MRR | Recall@5 | Precision@5 |
|---|---:|---:|---:|---:|
| Vector | 100.00% | 0.64 | 75.00% | 47.78% |
| PostgreSQL full-text only | 11.11% | 0.11 | 5.56% | 11.11% |
| **Hybrid (RRF)** | **100.00%** | **0.71** | 75.00% | 47.78% |
| Hybrid + reranker | not yet benchmarked | | | |

With hybrid retrieval, citation relevance and citation integrity were both 100% on this set. By question language, hybrid MRR was 0.79 for English and 0.62 for Vietnamese.

**How to read these numbers.** The dataset is small and targets a single long document, so Hit@5 is already saturated and MRR is the metric that separates methods. Treat the benchmark as a regression check for retrieval changes, not as a claim about general accuracy. The strict AND semantics of PostgreSQL `plainto_tsquery` explain why full-text search alone performs poorly on natural-language questions; it contributes mainly as the lexical half of the hybrid.

To reproduce locally, ingest the same PDF and update the `user_id` fields in `backend/evaluation/datasets/rag_eval.json`.

---

## Tech Stack

| Area | Technology |
|---|---|
| API | Python 3.13, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Data | PostgreSQL 16, pgvector, PostgreSQL full-text search (GIN) |
| Async | Celery, Redis (broker, pub/sub) |
| AI | NVIDIA NIM embeddings (`nemotron-3-embed-1b`), Groq (`openai/gpt-oss-120b`) |
| Documents | PyMuPDF |
| Frontend | React 19, Vite, TypeScript, i18next, react-markdown; Streamlit client |
| Quality | pytest, GitHub Actions |
| Ops | Docker, Docker Compose, Nginx |

---

## Quick Start (Docker)

The Compose stack runs PostgreSQL (pgvector), Redis, the API, and a Celery worker.

```bash
git clone https://github.com/11Khoa/askmemind.git
cd askmemind
cp .env.example .env
```

Edit `.env` and set at least:

```env
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql+psycopg://askmemind:change-me@postgres:5432/askmemind
SECRET_KEY=<long random string>
NVIDIA_API_KEY=<your NVIDIA API key>
GROQ_API_KEY=<your Groq API key>

# Recommended for best retrieval quality (see Configuration)
EMBEDDING_V2_ENABLED=True
HYBRID_SEARCH_ENABLED=True
```

Start the stack and apply migrations:

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

The API is now available at `http://127.0.0.1:8000` (OpenAPI docs at `/docs`). Run the web client:

```bash
cd frontend/react
cp .env.example .env     # leave VITE_API_URL empty to use the Vite /api proxy
npm install
npm run dev              # http://localhost:5173
```

Requires Node.js 20.19 or newer. To use the Streamlit client instead: `cd frontend/streamlit && pip install -r requirements.txt && streamlit run app.py`.

---

## Local Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

docker compose up -d postgres redis      # infrastructure only
cp .env.example .env                     # point DATABASE_URL and REDIS_URL to localhost

cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload                       # API
celery -A app.core.celery_app worker --loglevel=INFO          # worker (second terminal)
```

---

## Configuration

All settings are environment variables (see `.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `SECRET_KEY` | required | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime |
| `ENABLE_REGISTRATION` | `True` (`False` in `.env.example`) | Allow new sign-ups |
| `NVIDIA_API_KEY` / `GROQ_API_KEY` | empty | Provider credentials |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | `nvidia/nemotron-3-embed-1b` / `2048` | Embedding model (must match the v2 vector columns) |
| `EMBEDDING_V2_ENABLED` | `False` | Use v2 vectors for retrieval. When `False`, retrieval falls back to full-text only |
| `HYBRID_SEARCH_ENABLED` | `False` | Fuse vector and full-text results with RRF (requires v2) |
| `RERANKER_ENABLED` / `RERANKER_CANDIDATE_K` | `False` / `20` | Heuristic second-stage reranking |
| `AGENTIC_RETRIEVAL_ENABLED` | `False` | Bounded query-rewrite retry loop |
| `AGENTIC_RETRIEVAL_MAX_RETRIES` / `_MIN_CONFIDENCE` | `1` / `0.35` | Retry limits |
| `RETRIEVAL_MIN_CONFIDENCE` | `0.05` | Below this, return the no-answer response |
| `CITATION_VALIDATION_ENABLED` | `True` | Reject answers with invalid citations |
| `LLM_MODEL` / `LLM_MAX_TOKENS` | `openai/gpt-oss-120b` / `500` | Generation settings |
| `MAX_UPLOAD_SIZE_MB` | `25` | Upload limit |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and pub/sub |

**Why the flags default to off.** The retrieval stack moved from 1024-dimension embeddings to 2048-dimension v2 embeddings using an expand-and-backfill rollout so existing data is never broken. New installations can enable `EMBEDDING_V2_ENABLED` and `HYBRID_SEARCH_ENABLED` immediately. Existing installations should follow the runbook in [`backend/docs/embedding_v2_rollout.md`](backend/docs/embedding_v2_rollout.md) to backfill vectors first.

Enable the reranker and retry loop only after running the evaluation on your own documents.

---

## API Overview

| Group | Endpoint | Description |
|---|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Account and token |
| | `POST /auth/refresh`, `POST /auth/logout` | Rotate/revoke the HttpOnly refresh cookie; trusted Origin and CSRF header required |
| | `POST /auth/token/login`, `/auth/token/refresh`, `/auth/token/logout` | Optional JSON token flow for CLI/native clients; disabled by default |
| | `POST /auth/forgot-password`, `POST /auth/reset-password` | Email-based password recovery |
| Documents | `POST /documents/upload` | Validate and enqueue a PDF (returns `202`) |
| | `POST /documents/{id}/retry` | Retry a failed document in place (returns `202`, same DocumentRead) |
| | `GET /documents`, `GET /documents/{id}` | List and inspect documents |
| | `GET /documents/events` | SSE stream of document status changes |
| | `DELETE /documents/{id}` | Delete PDF, chunks/vectors and cached source excerpts |
| | `GET /documents/{id}/file` | Authenticated original PDF (inline, no-store) |
| | `GET /documents/{id}/chunks/{chunk_id}` | Authenticated source passage and page |
| Chats | `GET /chats`, `POST /chats` | Conversations |
| | `GET /chats/{id}/messages`, `POST /chats/{id}/messages` | Message history |
| | `POST /chats/{id}/questions` | Ask a question (single response) |
| | `POST /chats/{id}/questions/stream` | Ask a question (SSE: `token`, `replace`, `final`, `error`) |
| | `DELETE /chats/{id}` | Delete conversation and all its messages |
| Health | `GET /health/live`, `GET /health/ready` | Liveness and readiness (`SELECT 1`) |

Interactive documentation is served at `/docs`. A ready-made request collection is in `http/local-smoke.http`.

---

## Testing

```bash
cd backend
python -m pytest -q
```

The suite (40+ modules) covers services, repositories, routers, providers, guardrails, retrieval, reranking, the retrieval agent, and the evaluation metrics. CI runs Alembic migrations and the full suite against a `pgvector/pgvector:pg16` service on every push and pull request.

---

## Deployment

Recommended production layout: Nginx (HTTPS) in front of the API on `127.0.0.1`, with PostgreSQL and Redis not exposed publicly.

**Important: disable proxy buffering for the streaming route.** Nginx buffers upstream responses by default, which makes streamed answers arrive all at once instead of token by token. Add a dedicated location above your catch-all `location /`:

```nginx
location ~ ^/chats/.+/questions/stream {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    gzip off;
    proxy_read_timeout 300s;
}
```

The same applies to `/documents/events`. The API already sends `X-Accel-Buffering: no` on that route. A complete example with upload and rate limits is in `deploy/nginx/askmemind.conf.example`.

Checklist:
- Keep `.env` private; use a long random `SECRET_KEY`.
- Set `BACKEND_CORS_ORIGINS` and `AUTH_CSRF_TRUSTED_ORIGINS` to explicit frontend origins (no wildcards). Keep Secure refresh cookies enabled in production. See [Authentication](backend/docs/authentication.md) for local overrides and same-site deployment.
- The API and the Celery worker must share the upload directory (`storage/uploads`) unless you add object storage.
- Back up PostgreSQL and `storage/uploads`.
- Avoid `docker compose down -v` unless you intend to delete database volumes.

---

## Reliability and Observability

- Every response carries an `X-Request-ID`; JSON logs include the request ID and user ID across retrieval, reranking, generation and fallback events.
- Stage logs record latency, retrieval method, candidate counts, confidence, fallback reason, citation errors and provider token usage. Raw questions and document text are intentionally excluded from agent decision logs.
- `/health/live` and `/health/ready` back the Docker health checks; readiness returns `503` when PostgreSQL is unavailable.
- Failed documents can be retried in place from React. `POST /documents/{id}/retry` uses bearer authentication, requires no body and returns `202` with the same document ID, `status: processing`, a new `processing_attempt_id` and a cleared error. Other owners receive `403`, unknown IDs `404`, non-failed documents or an unavailable required PDF `409`, and broker failures `503` (the document remains retryable).
- A complete chunk checkpoint is committed before embedding; each successful `EMBEDDING_BATCH_SIZE` batch is committed independently. Retry preserves matching chunk IDs and valid v2 vectors, embedding only missing/outdated vectors. Legacy chunks without a completion checkpoint are reconciled against the original PDF first. Missing original files require re-upload when extraction is still needed.
- An atomic status transition rejects double retries. Worker advisory locks prevent concurrent processing of a document, and attempt IDs discard stale queued jobs. Only ready documents participate in retrieval.
- API restarts do not fail independent Celery jobs. Late acknowledgements and worker-loss rejection allow redelivery; Redis persistence and a shared upload volume are required. This is not an exactly-once queue or a substitute for durable object storage. Gracefully stop old workers before deploying the migration and new worker code together.
- SSE status payloads include `processing_attempt_id` and `updated_at`; React ignores stale updates and polls every 2 seconds while processing to recover missed Pub/Sub messages. Notification failures do not change a successful document to failed.

---

## Security

- Passwords are hashed with a modern adaptive algorithm; sessions use short-lived JWTs.
- Public sign-up always creates a `user`; only administrators can create accounts with selected roles. Existing accounts remain users until explicitly promoted. See [RBAC deployment and administrator bootstrap](backend/docs/rbac_and_admin.md).
- Browser login returns an access token in JSON and a persistent, host-only HttpOnly refresh cookie. Login/refresh/logout require a trusted Origin and `X-CSRF-Protection: 1`. Refresh tokens are stored as SHA-256 digests, rotated once per use with absolute session expiry, and revoked on logout. Reuse revokes all refresh sessions for that account. Optional JSON-token endpoints are isolated from browser cookie authentication.
- Protected requests check a Redis access-token blacklist. Redis outages return `503`; blacklist keys expire with the JWT. Password resets increment a DB token version to invalidate every existing access token and revoke all refresh tokens.
- Password recovery uses expiring, single-use tokens delivered over SMTP by Celery, with generic responses and Redis rate limits. Configure `PASSWORD_RESET_URL` and SMTP settings in both API and worker environments.
- See [Authentication](backend/docs/authentication.md) for payloads, configuration, deployment and the eight implementation lessons.
- Every retrieval query is joined on the owning user, so users cannot read each other's chunks.
- Uploads are limited by size, content type and `%PDF-` signature; files are stored under generated names.
- Login/registration and per-user questions/uploads have shared Redis rate limits. Per-user document/storage quotas and worker PDF page/text limits are configurable. See [backend limits and deployment](backend/docs/backend_hardening.md), including the chat counter migration rollout.
- Document context is delimited as untrusted input in the prompt, and the model is instructed never to follow instructions found inside documents.
- Never commit `.env` or credentials; rotate any secret that may have been exposed.

---

## Known Limitations

- Chunking is fixed-size (1000 characters, 200 overlap) and does not follow sentence or section boundaries.
- Streaming tokens are provisional; citation validation can replace the answer before the final event is saved. Clients must handle the `replace` event. Citation checks validate source identifiers, not semantic faithfulness.
- Real-time status updates use Redis pub/sub, which does not replay missed events. The client reconnects with bounded backoff and reconciles known document statuses. See [SSE recovery and proxy settings](backend/docs/sse_recovery.md).
- The reranker and query rewriter are heuristic, and the evaluation set covers one document. See [Evaluation](#evaluation).
- Uploads use local disk rather than object storage.
- Metrics export and distributed tracing are not configured; logs go to stdout.

---

## Roadmap

- Object storage for uploaded PDFs.
- Larger, multi-document evaluation set with answer-faithfulness scoring.
- Compare the heuristic reranker against a cross-encoder.
- SSE reconnect and state resync on the client.
- Sentence- and section-aware chunking.
- Prometheus metrics and OpenTelemetry traces.

---

## Project Structure

```text
backend/
  app/
    agents/         bounded retrieval state machine
    core/           config, security, dependencies, Celery, logging
    models/         SQLAlchemy models
    repositories/   database access
    routers/        HTTP endpoints
    schemas/        Pydantic request and response models
    services/       RAG pipeline, retrieval, guardrails, providers
    tasks/          Celery tasks
  alembic/          database migrations
  evaluation/       dataset, metrics, runner, generated reports
  docs/             operational runbooks
  tests/            pytest suite
frontend/
  react/            web client (Vite, TypeScript)
  streamlit/        lightweight client
deploy/nginx/       reverse proxy example
http/               smoke-test requests and sample PDFs
docker-compose.yml  PostgreSQL, Redis, API, worker
```

---

## Author

Built by **Khoa** ([@11Khoa](https://github.com/11Khoa)).
