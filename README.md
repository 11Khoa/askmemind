# AskMeMind

<img width="1865" height="1393" alt="image" src="https://github.com/user-attachments/assets/944de9b4-21d9-4614-b2de-849ba255eb7b" />
<br>
AskMeMind is a PDF question-answering platform built around Retrieval-Augmented Generation (RAG). Users can upload PDFs, extract searchable text, generate embeddings, retrieve relevant document chunks, and ask questions with citation-aware answers.

```mermaid
flowchart TD

subgraph group_client["Client Surface"]
  node_streamlit["Streamlit Client<br/>[app.py]"]
end

subgraph group_api["API and Identity"]
  node_auth_api["Auth API<br/>[auth.py]"]
  node_document_api["Document API<br/>[document.py]"]
  node_upload_api["Upload API<br/>[upload.py]"]
  node_chat_api["Chat API<br/>[chat.py]"]
  node_auth_service["Auth Service<br/>[auth_service.py]"]
  node_security["JWT Security<br/>[security.py]"]
end

subgraph group_ingest["Document Ingestion"]
  node_document_service["Document Service"]
  node_processing["PDF Processing"]
  node_file_storage["File Storage"]
  node_pdf_extract["PDF Extraction"]
  node_chunking["Chunk Service<br/>[chunk_service.py]"]
end

subgraph group_rag["RAG Answering"]
  node_embedding["Embedding Service"]
  node_rag_service["RAG Service<br/>[rag_service.py]"]
  node_retrieval["Retrieval Service"]
  node_context["Context Builder"]
  node_llm["LLM Service<br/>[llm_service.py]"]
end

subgraph group_storage["Persistence and Providers"]
  node_document_repo["Document Repository"]
  node_chunk_repo["Chunk Repository"]
  node_chat_repo["Chat Repository<br/>[chat_repository.py]"]
  node_postgres[("PostgreSQL pgvector")]
  node_nvidia["NVIDIA Embeddings"]
  node_groq["Groq LLM"]
end

node_user(("User"))

node_user -->|"uses"| node_streamlit
node_streamlit -->|"authenticates"| node_auth_api
node_streamlit -->|"uploads PDF"| node_upload_api
node_streamlit -->|"lists documents"| node_document_api
node_streamlit -->|"asks questions"| node_chat_api
node_auth_api -->|"handles auth"| node_auth_service
node_auth_service -->|"creates tokens"| node_security
node_auth_service -->|"stores users"| node_postgres
node_upload_api -->|"starts upload"| node_document_service
node_document_service -->|"saves file"| node_file_storage
node_document_service -->|"processes PDF"| node_processing
node_processing -->|"reads file"| node_file_storage
node_processing -->|"extracts pages"| node_pdf_extract
node_processing -->|"creates chunks"| node_chunking
node_processing -->|"embeds passages"| node_embedding
node_processing -->|"updates status"| node_document_repo
node_processing -->|"persists chunks"| node_chunk_repo
node_embedding -.->|"calls embeddings"| node_nvidia
node_document_repo -->|"reads writes"| node_postgres
node_chunk_repo -->|"stores vectors"| node_postgres
node_document_api -->|"queries documents"| node_document_repo
node_chat_api -->|"answers question"| node_rag_service
node_rag_service -->|"retrieves chunks"| node_retrieval
node_retrieval -->|"embeds query"| node_embedding
node_retrieval -->|"searches chunks"| node_chunk_repo
node_rag_service -->|"builds context"| node_context
node_rag_service -->|"generates answer"| node_llm
node_llm -.->|"calls completion"| node_groq
node_chat_api -->|"persists messages"| node_chat_repo
node_chat_repo -->|"stores chats"| node_postgres
node_rag_service -->|"returns citations"| node_chat_api

click node_streamlit "https://github.com/11khoa/askmemind/blob/master/frontend/streamlit/app.py"
click node_auth_api "https://github.com/11khoa/askmemind/blob/master/backend/app/routers/auth.py"
click node_document_api "https://github.com/11khoa/askmemind/blob/master/backend/app/routers/document.py"
click node_upload_api "https://github.com/11khoa/askmemind/blob/master/backend/app/routers/upload.py"
click node_chat_api "https://github.com/11khoa/askmemind/blob/master/backend/app/routers/chat.py"
click node_auth_service "https://github.com/11khoa/askmemind/blob/master/backend/app/services/auth_service.py"
click node_security "https://github.com/11khoa/askmemind/blob/master/backend/app/core/security.py"
click node_document_service "https://github.com/11khoa/askmemind/blob/master/backend/app/services/document_service.py"
click node_processing "https://github.com/11khoa/askmemind/blob/master/backend/app/services/document_processing_service.py"
click node_file_storage "https://github.com/11khoa/askmemind/blob/master/backend/app/services/file_storage_service.py"
click node_pdf_extract "https://github.com/11khoa/askmemind/blob/master/backend/app/services/extraction/pdf_extraction_service.py"
click node_chunking "https://github.com/11khoa/askmemind/blob/master/backend/app/services/chunk_service.py"
click node_embedding "https://github.com/11khoa/askmemind/blob/master/backend/app/services/embedding_service.py"
click node_rag_service "https://github.com/11khoa/askmemind/blob/master/backend/app/services/rag_service.py"
click node_retrieval "https://github.com/11khoa/askmemind/blob/master/backend/app/services/retrieval_service.py"
click node_context "https://github.com/11khoa/askmemind/blob/master/backend/app/services/context_builder_service.py"
click node_llm "https://github.com/11khoa/askmemind/blob/master/backend/app/services/llm_service.py"
click node_document_repo "https://github.com/11khoa/askmemind/blob/master/backend/app/repositories/document_repository.py"
click node_chunk_repo "https://github.com/11khoa/askmemind/blob/master/backend/app/repositories/chunk_repository.py"
click node_chat_repo "https://github.com/11khoa/askmemind/blob/master/backend/app/repositories/chat_repository.py"
click node_nvidia "https://github.com/11khoa/askmemind/blob/master/backend/app/services/providers/nvidia_embedding_provider.py"
click node_groq "https://github.com/11khoa/askmemind/blob/master/backend/app/services/providers/groq_llm_provider.py"

classDef toneNeutral fill:#f8fafc,stroke:#334155,stroke-width:1.5px,color:#0f172a
classDef toneBlue fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef toneAmber fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef toneMint fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef toneRose fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef toneIndigo fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81
classDef toneTeal fill:#ccfbf1,stroke:#0f766e,stroke-width:1.5px,color:#134e4a
class node_streamlit,node_user toneBlue
class node_auth_api,node_document_api,node_upload_api,node_chat_api,node_auth_service,node_security toneAmber
class node_document_service,node_processing,node_file_storage,node_pdf_extract,node_chunking toneMint
class node_embedding,node_rag_service,node_retrieval,node_context,node_llm toneRose
class node_document_repo,node_chunk_repo,node_chat_repo,node_postgres,node_nvidia,node_groq toneIndigo
```
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

AskMeMind is currently an MVP.

Implemented:

- User registration and login with Bearer JWT authentication
- PDF upload and local file storage
- PDF text extraction
- Text chunking with citation fields
- Embedding generation
- pgvector storage and similarity search
- Retrieval-first RAG answer generation
- Chat and message persistence
- Local smoke-test requests
- Backend test suite

Not included yet:

- Background processing with Celery and Redis
- Streaming assistant responses
- Document deletion
- Multi-document chat
- Object storage for uploaded files
- Production observability
- Full production frontend

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
Upload PDF
  -> save uploaded file
  -> create document record
  -> extract page-aware text
  -> split text into chunks
  -> generate passage embeddings
  -> store chunks, vectors, and embedding metadata
  -> receive user question
  -> generate query embedding
  -> retrieve relevant chunks
  -> build grounded context
  -> generate answer
  -> persist chat messages and citations
~~~

AskMeMind is intentionally retrieval-first. If no relevant document chunks are found, the system returns a fallback answer instead of asking the LLM to answer from general knowledge.

## Project Structure

~~~text
backend/app/
  core/          configuration, security, dependencies, unit of work
  models/        SQLAlchemy ORM models
  repositories/  database access layer
  routers/       FastAPI HTTP endpoints
  schemas/       Pydantic request and response schemas
  services/      business logic, RAG pipeline, provider integrations

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

Storage settings:

~~~env
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

- PDF processing and embedding generation are synchronous in the MVP.
- Upload validation currently supports PDFs only.
- The vector dimension is fixed at 1024 in the current schema.
- Chat history is append-only; message deletion is intentionally out of scope.
- Production concerns such as async job orchestration, object storage, and observability are future work.

## Roadmap

- Move PDF processing and embedding generation to Celery workers.
- Add Redis-backed job status tracking.
- Add a polished frontend for upload, document listing, and chat.
- Add document deletion with file and chunk cleanup.
- Add streaming assistant responses.
- Support multiple documents in a single chat.
- Add richer citation display.
- Prepare deployment configuration for production operations.

## Development Notes

- RAG answers must go through retrieval; do not answer directly from the LLM when document grounding is required.
- `chunk_metadata` may be empty for PDF chunks because PDF citations are stored in normalized fields such as `page_number`, `start_char`, and `end_char`.
- PDF chunks store embedding provider, model, and dimension metadata to support future re-embedding workflows.
- Celery and Redis are planned for long-running document processing, but they are not wired into the current MVP.
