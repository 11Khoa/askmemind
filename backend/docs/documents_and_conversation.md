# Document management, sources and follow-up questions

All endpoints require the existing bearer authentication and check the owner.
Unknown IDs return 404; another owner's resources return 403.

## Deletion

`DELETE /chats/{chat_id}` returns 204 and cascades to every message. Uploaded
documents belong to the user independently and are retained.

`DELETE /documents/{document_id}` returns 204 after removing the original PDF,
document, chunks and embedding vectors. It also clears stored retrieval context
and removes matching citation metadata from the owner's saved assistant messages.
Historical question/answer text is retained; delete those conversations to remove
it too. A missing original file does not prevent deletion.

Deletion uses the document worker's advisory lock. An active processing task
causes 409: wait for it to finish and retry. A queued task can be deleted; when
delivered, the worker ignores the missing/deleting document. Before removing
files, the document is committed as `deleting` with no active processing attempt.
Retrieval and source endpoints exclude it. If disk cleanup fails, DELETE returns
503; repeat DELETE to finish. A crash between cleanup and row deletion is also
recoverable this way. Pending deletions count toward quotas until complete.
No background cleanup scheduler is needed, but pending deletions require a retry.

An answer finishing after its source was deleted is replaced at persistence with
a source-unavailable response. Such turns and turns with deleted source metadata
are excluded from future conversation context. Already open browser PDFs and
already streamed provisional tokens cannot be retracted by server-side deletion.

## Source inspection

`GET /documents/{document_id}/chunks/{chunk_id}` returns `id`, `document_id`,
`content`, `page_number` and `chunk_index`. The document must be ready and the
chunk must belong to that document. It returns no embedding vectors.

`GET /documents/{document_id}/file` returns the original PDF with inline
disposition, `application/pdf`, `Cache-Control: no-store`, and `nosniff`.
The browser fetches it using its bearer session and creates a temporary blob URL
for the PDF viewer. `#page=N` selects the cited page in browsers with native PDF
support. Never put access tokens in query parameters; revoke blob URLs on close.

## Conversation context

The server loads up to `CONVERSATION_HISTORY_TURNS` completed prior turns
(default 6), within `CONVERSATION_HISTORY_CHARACTERS` total characters (12000).
It uses only the current chat and the exact selected document scope. Changing
between a specific document and all documents starts a separate context scope.
Incomplete/concurrent later turns and turns with deleted sources are excluded.
Older turns without scope metadata are eligible only in the all-documents scope.

Recent dialogue enriches retrieval for short follow-ups. If the combined query
has no hits (for example strict lexical AND search), bounded fallback queries try
the current question and then the prior user question. Current evidence is always
retrieved again. Dialogue is sent as prior user/assistant messages to generation;
the system prompt explicitly prohibits treating old answers or old source numbers
as evidence. Citation validation continues to use only the newly retrieved sources.
This is bounded dialogue context, not an unlimited memory or a semantic verifier.

No new migration is required beyond backend hardening's `e2a6d891bc04`.
Deploy `feature/backend` before the matching `feature/frontend-react` client.
