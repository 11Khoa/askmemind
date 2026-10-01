# AskMeMind
<img width="881" height="554" alt="image" src="https://github.com/user-attachments/assets/17b2fa5c-f525-4fd0-90fb-698a643ce36c" />

<br>
AskMeMind is a PDF question-answering platform built around Retrieval-Augmented Generation (RAG). Users can upload PDFs, extract searchable text, generate embeddings, retrieve relevant document chunks, and ask questions with citation-aware answers.  
<br><br>

[![Architecture diagram of 11khoa/askmemind](https://gitdiagram.com/11khoa/askmemind/diagram.png)](https://gitdiagram.com/11khoa/askmemind?utm_source=readme&utm_medium=picture)
[![Architecture diagram](https://gitdiagram.com/diagram-badge.svg)](https://gitdiagram.com/11khoa/askmemind?utm_source=readme&utm_medium=badge)

## Highlights

- Authenticated PDF upload and document management
- Page-aware PDF extraction with PyMuPDF
- Chunking with document, page, and character traceability
- NVIDIA NIM embeddings stored in PostgreSQL with pgvector
- Vector similarity retrieval scoped to the authenticated user
- Groq chat-completion integration for grounded answers
- Chat history persistence with assistant citation metadata
- Alembic migrations for schema evolution
- Docker Compose setup for FastAPI and PostgreSQL/pgvector
- Pytest coverage for core services, repositories, routers, and providers

## Status

AskMeMind is a production-oriented RAG portfolio backend. It implements the
reliability, evaluation, and operational boundaries expected from an applied AI
service while keeping asynchronous jobs and distributed infrastructure out of
scope.

Implemented:

- JWT-authenticated, user-isolated document and chat workflows
- Size-limited PDF upload, signature validation, extraction, and chunking
- NVIDIA embeddings in PostgreSQL with pgvector
- PostgreSQL full-text search with a GIN index
- Vector, lexical, and weighted RRF hybrid retrieval
- Configurable second-stage heuristic reranking
- Confidence fallback, citation validation, and prompt-injection isolation
- Bounded self-correcting retrieval with explicit search and rewrite tools
- JSON request and RAG stage logs with request IDs, latency, and token usage
- Reproducible retrieval evaluation with JSON, CSV, and Markdown reports
- Liveness/readiness endpoints and Docker health checks
- Unit, workflow, repository, and API integration tests

Intentionally out of scope:

- Horizontally scaled document workers beyond the bundled single Celery worker
- Streaming assistant responses
- Object storage and horizontal worker scaling
- A full production frontend

The `frontend/streamlit` directory contains a lightweight Streamlit client for local interaction. The core product surface is still the FastAPI backend.

## Tech Stack

- Python 3.13+
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- pgvector
- PyMuPDF
- NVIDIA NIM embeddings
- Groq chat completions
- Streamlit client prototype
- Pytest
- Docker Compose

## Architecture

~~~text
Client
  -> FastAPI router
  -> Service layer
  -> Repository layer
  -> PostgreSQL / pgvector
~~~

The backend follows clean architecture principles:

- Routers handle HTTP input, output, validation boundaries, and status codes.
- Services own business rules, orchestration, and RAG workflow decisions.
- Repositories isolate SQLAlchemy database access.
- Provider classes isolate external AI API calls.
- Models and schemas are kept separate.

## RAG Pipeline

~~~text
PDF upload
  -> validate size, content type, and PDF signature
  -> extract page-aware text
  -> chunk and embed passages
  -> persist text, metadata, and vectors
  -> vector search + PostgreSQL FTS
  -> weighted reciprocal-rank fusion
  -> optional bounded query rewrite and retry
  -> optional heuristic reranking
  -> confidence guardrail
  -> build citation-aware context
  -> grounded LLM answer
  -> validate cited source numbers
  -> persist answer and citations
~~~

Vector search handles semantic similarity; PostgreSQL full-text search handles
exact terms, names, and abbreviations. Hybrid mode combines their rank positions
with weighted reciprocal-rank fusion, so incompatible raw score scales never
need to be normalized together. The optional reranker then scores a larger
candidate pool using keyword overlap, original rank, and phrase matches.

When agentic retrieval is enabled, a Python state machine calls the retrieval
tool, grades the evidence, rewrites weak queries into deterministic keywords,
and retries at most the configured number of times. It keeps the strongest
result seen and logs each decision. This avoids unbounded loops and avoids an
extra LLM call solely for query rewriting.

The answer path is retrieval-first. Empty or low-confidence evidence returns a
stable no-answer response without calling the LLM. Generated answers must cite
source markers that exist in the built context; invalid citations also trigger
the fallback. Document context is delimited as untrusted data in the generation
prompt.

## Evaluation

Run the complete retrieval comparison from the backend directory:

```bash
python -m evaluation.run_evaluation
```

The command evaluates vector, PostgreSQL full-text, hybrid, and
hybrid-plus-reranker retrieval. It writes per-method JSON, CSV, and Markdown
reports plus comparison files to `backend/evaluation/reports/`. Retrieval
reports include Hit@K, MRR, Recall@K, Precision@K, retrieval latency, and
retrieved chunk count. Answer success is included when
`RUN_ANSWER_EVALUATION` is enabled.

The last successful pre-latency benchmark used 18 English and Vietnamese
questions at `K=5`:

| Method | Hit@5 | MRR | Recall@5 | Precision@5 | Latency |
|---|---:|---:|---:|---:|---:|
| Vector | 100.00% | 0.64 | 75.00% | 47.78% | Not captured |
| PostgreSQL FTS | 11.11% | 0.11 | 5.56% | 11.11% | 9.93 ms |
| Hybrid RRF | 100.00% | 0.71 | 75.00% | 47.78% | Not captured |
| Hybrid + reranker | Pending provider availability | - | - | - | - |

## Reliability and Observability

Every HTTP response includes an `X-Request-ID`. JSON logs carry that request ID
and the authenticated user ID across retrieval, reranking, generation, and
fallback events. Stage logs include latency, retrieval method, candidate counts,
confidence, fallback reason, citation errors, and provider token usage. Raw
questions and document text are deliberately excluded from agent decision logs.

Operational probes:

- `GET /health/live` confirms that the API process can serve requests.
- `GET /health/ready` runs `SELECT 1` and returns 503 when PostgreSQL is unavailable.
- Docker Compose waits for PostgreSQL readiness and health-checks the backend.

## Project Structure

~~~text
backend/app/
  core/          configuration, security, dependencies, unit of work
  agents/        bounded retrieval state machine and tool boundaries
  models/        SQLAlchemy ORM models
  repositories/  database access layer
  routers/       FastAPI HTTP endpoints
  schemas/       Pydantic request and response schemas
  services/      business logic, RAG pipeline, provider integrations

backend/evaluation/ datasets, metrics, runner, and generated reports
backend/tests/   pytest test suite
frontend/        Streamlit client prototype
http/            local smoke-test requests and sample PDFs
deploy/          deployment examples such as Nginx reverse proxy config
~~~

## API Overview

Auth:

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

Documents:

- `POST /documents/upload`
- `GET /documents`
- `GET /documents/{document_id}`

Chats:

- `POST /chats`
- `GET /chats`
- `POST /chats/{chat_id}/messages`
- `GET /chats/{chat_id}/messages`
- `POST /chats/{chat_id}/questions`

Health:

- `GET /health/live`
- `GET /health/ready`

After the backend is running, the OpenAPI docs are available at:

~~~text
http://127.0.0.1:8000/docs
~~~

## Quick Start With Docker

Create a local `.env` file:

~~~bash
cp .env.example .env
~~~

Fill the required values:

~~~env
POSTGRES_USER=askmemind
POSTGRES_PASSWORD=change-me
POSTGRES_DB=askmemind

DATABASE_URL=postgresql+psycopg://askmemind:change-me@postgres:5432/askmemind
SECRET_KEY=change-me-to-a-long-random-secret
NVIDIA_API_KEY=replace-with-nvidia-api-key
GROQ_API_KEY=replace-with-groq-api-key
BACKEND_CORS_ORIGINS=http://localhost:3000
~~~

Start the stack:

~~~bash
docker compose up -d --build
~~~

Run migrations:

~~~bash
docker compose exec backend alembic upgrade head
~~~

Check the active migration:

~~~bash
docker compose exec backend alembic current
~~~

View backend logs:

~~~bash
docker compose logs backend --tail=80
~~~

## Local Python Development

Use this flow when developing or running tests outside Docker.

Create and activate a virtual environment:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
~~~

Install backend dependencies:

~~~bash
pip install -r backend/requirements.txt
~~~

Start PostgreSQL with pgvector:

~~~bash
docker compose up -d postgres
~~~

Create `.env` from `.env.example` and point `DATABASE_URL` to localhost:

~~~env
DATABASE_URL=postgresql+psycopg://askmemind:change-me@localhost:5432/askmemind
SECRET_KEY=replace-with-local-secret
NVIDIA_API_KEY=replace-with-nvidia-api-key
GROQ_API_KEY=replace-with-groq-api-key
~~~

Run migrations:

~~~bash
cd backend
../.venv/bin/alembic upgrade head
~~~

Start the API:

~~~bash
cd backend
../.venv/bin/python -m uvicorn app.main:app --reload
~~~

## Configuration Reference

Embedding settings must stay aligned with the database vector schema:

~~~env
EMBEDDING_PROVIDER=nvidia
EMBEDDING_MODEL=nvidia/llama-nemotron-embed-1b-v2
EMBEDDING_BASE_URL=https://integrate.api.nvidia.com/v1
EMBEDDING_DIMENSIONS=1024
~~~

LLM settings:

~~~env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MAX_TOKENS=500
~~~

Retrieval, reliability, and agent settings:

~~~env
HYBRID_SEARCH_ENABLED=false
RERANKER_ENABLED=false
RERANKER_CANDIDATE_K=20
RETRIEVAL_MIN_CONFIDENCE=0.05
CITATION_VALIDATION_ENABLED=true
AGENTIC_RETRIEVAL_ENABLED=false
AGENTIC_RETRIEVAL_MAX_RETRIES=1
AGENTIC_RETRIEVAL_MIN_CONFIDENCE=0.35
~~~

The hybrid, reranking, and agentic features are independent flags. Enable them
after running the evaluation command against your own documents and questions.

Storage settings:

~~~env
MAX_UPLOAD_SIZE_MB=25
UPLOAD_DIR=storage/uploads
TEMP_DIR=storage/temp
~~~

## Tests

Run the backend test suite:

~~~bash
cd backend
../.venv/bin/python -m pytest -q
~~~

## Smoke Test

Use the local smoke file:

~~~text
http/local-smoke.http
~~~

Recommended flow:

1. Register or login.
2. Copy `access_token` into `@accessToken`.
3. Create a chat.
4. Copy the chat `id` into `@chatId`.
5. Upload a PDF.
6. Copy the document `id` into `@documentId`.
7. Ask a RAG question with `POST /chats/{chat_id}/questions`.
8. Verify persisted messages with `GET /chats/{chat_id}/messages`.

The RAG smoke request calls real external services:

- NVIDIA API for passage and query embeddings
- PostgreSQL/pgvector for retrieval
- Groq API for answer generation

## Deployment Notes

The repository includes deployment skeletons that are safe to publish:

- `backend/Dockerfile` builds the FastAPI backend runtime image.
- `docker-compose.yml` runs the backend and PostgreSQL/pgvector services.
- `.env.example` documents required environment variables without secrets.
- `deploy/nginx/askmemind.conf.example` provides an example reverse proxy with upload and rate limits.

For a public VPS deployment:

- Keep `.env` private and never commit real API keys, database passwords, or `SECRET_KEY`.
- Point `DATABASE_URL` to the Docker Compose service host `postgres`.
- Do not expose PostgreSQL port `5432` to the internet.
- Put the backend behind Nginx or Caddy with HTTPS.
- Bind the backend port to localhost when using a reverse proxy, for example `127.0.0.1:8000:8000`.
- Set `BACKEND_CORS_ORIGINS` to the frontend domain, such as a Vercel URL or custom domain.
- Keep uploaded files out of git and back up `storage/uploads` if the data matters.

If PostgreSQL data already exists and you need to change `POSTGRES_PASSWORD`, update the database user first:

~~~bash
docker compose exec postgres psql -U askmemind -d askmemind
~~~

Then run:

~~~sql
ALTER USER askmemind WITH PASSWORD 'new-password';
~~~

Update both `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env`, then recreate the backend:

~~~bash
docker compose up -d --force-recreate backend
~~~

Do not use `docker compose down -v` unless you intentionally want to delete Docker volumes, including PostgreSQL data.

## Security Notes

- Never commit `.env`, real API keys, database passwords, or JWT secrets.
- Keep uploaded files and temporary files out of git.
- Restrict upload types and sizes before exposing the service publicly.
- Use HTTPS in production.
- Use a strong random `SECRET_KEY` for JWT signing.
- Rotate any credential that may have been committed or shared accidentally.

## Current Limitations

- PDF uploads return after validation and persistence; PDF processing runs in a Celery worker backed by Redis. The API uses Redis pub/sub to stream document status updates over SSE. API and worker containers must share access to uploaded files, and production deployments should tune Celery retries, queues, and worker concurrency for their workload. Startup cleanup marks documents left in processing as processing_failed.
- Uploads use local disk rather than durable object storage.
- The vector dimension is fixed at 1024; changing embedding models requires a migration and full re-embedding.
- The deterministic query rewriter is transparent and cheap, but less flexible than a separately evaluated model-based rewriter.
- Chat history is append-only, and answer streaming is not implemented.
- Structured logs are emitted to stdout; metrics export and distributed tracing are not configured.

## Next Steps

- Add richer Celery retry/backoff policies, worker dashboards, and per-task progress metadata.
- Add object storage and document deletion with file/chunk cleanup.
- Evaluate a replacement embedding model and re-index existing chunks before changing the configured model.
- Compare the heuristic reranker with a cross-encoder on the checked-in dataset.
- Export OpenTelemetry traces and Prometheus metrics when deployment requirements justify them.
- Add streaming responses and a polished frontend.

## Development Notes

- RAG answers must go through retrieval; do not answer directly from the LLM when document grounding is required.
- `chunk_metadata` may be empty for PDF chunks because PDF citations are stored in normalized fields such as `page_number`, `start_char`, and `end_char`.
- PDF chunks store embedding provider, model, and dimension metadata to support future re-embedding workflows.
- Celery and Redis handle long-running document processing; keep the API and worker on shared upload storage unless object storage is added.
