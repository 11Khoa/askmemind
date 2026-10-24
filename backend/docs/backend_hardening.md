# Chat consistency and resource limits

## Deployment

Stop/drain old API processes (including active question streams), run
`alembic upgrade head`, then start the new API. Migration `e2a6d891bc04` adds
`chats.next_message_index` and initializes it from existing messages. Do not run
old and new message writers together: old writers do not reserve pending answer
positions. The worker must receive the PDF limit settings too.

Each question atomically reserves two positions in PostgreSQL before retrieval
or generation. User and assistant messages remain adjacent when requests overlap.
The reservation commits immediately; no chat row lock is held during AI calls.
Errors or cancellations may leave unused positions. Retrying a request starts a
new turn; this change does not provide request idempotency or automatic recovery
of an interrupted generation.

Streaming tokens are provisional. When citation validation is enabled, the final
answer is checked using the same rules as non-streaming answers. Invalid answers
emit `replace` with the no-answer response before `final`; only that final answer
is saved. Clients must handle `replace`. Validation checks source identifiers,
not semantic support for every claim. Unexpected stream errors return a generic
message and request ID; details are logged on the server.

## Defaults

| Setting | Default | Scope |
| --- | --- | --- |
| `LOGIN_REQUESTS_PER_MINUTE` | 10 | Per peer IP, shared browser/JSON login budget |
| `REGISTER_REQUESTS_PER_HOUR` | 5 | Per peer IP |
| `QUESTION_REQUESTS_PER_MINUTE` | 30 | Per user, shared across questions, streaming and raw messages |
| `UPLOAD_REQUESTS_PER_HOUR` | 20 | Per user, shared uploads and processing retries |
| `MAX_DOCUMENTS_PER_USER` | 100 | All document statuses, including failed documents |
| `MAX_STORAGE_PER_USER_MB` | 500 | Sum of original PDF sizes, in MiB |
| `MAX_PDF_PAGES` | 500 | Checked in the worker before page extraction |
| `MAX_PDF_TEXT_CHARACTERS` | 2000000 | Cumulative extracted text per PDF |

Chat content is limited to 8000 characters; longer input returns `422`.
The existing `MAX_UPLOAD_SIZE_MB` still limits each file.

Redis fixed-window counters are shared across API processes. Windows begin on
the first request and expire after 60/3600 seconds; rejected requests count too.
Exceeding a rate limit returns `429` with a conservative `Retry-After` equal to
the window length. Redis failures fail closed with `503`. IP-based budgets can
be shared by users behind a NAT. Configure Uvicorn to trust forwarded addresses
only from the actual reverse proxy, and block public access to the API port.
The application does not directly trust client `X-Forwarded-For` headers.

Storage/count checks lock the owning user row until document insertion commits,
so concurrent uploads cannot both consume the final quota slot. A quota rejection
returns `409`, removes the newly saved file and does not enqueue processing.
Existing documents are not removed when limits are lowered. Page/text violations
mark the asynchronous document job failed. These limits do not impose a hard
memory/CPU sandbox on native PDF parsing, nor replace global disk monitoring or
provider spend limits. Document deletion is still a separate feature.
