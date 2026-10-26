# Document SSE lifecycle and recovery

`GET /documents/events` is a live Redis Pub/Sub subscription, not a durable event
log. Redis messages missed while disconnected cannot be replayed.

The backend sends a comment heartbeat at least every 15 seconds while waiting,
rotates a connection after roughly 240 seconds, and closes Redis handles on exit
(including subscription failure and browser cancellation). Redis connection setup
has a five-second timeout. Authentication is checked on each new connection, so
an old open stream does not bypass role/session changes indefinitely. The database
session used for authentication is closed before waiting on Redis; idle streams
do not pin database pool connections. Headers disable intermediary transformation
and Nginx buffering. Redis outages close the stream for client-driven recovery.

The React document subscriber reconnects on both transport failure and clean EOF,
using exponential backoff with jitter capped at 30 seconds. A watchdog reconnects
after 45 seconds without any bytes (comments count as activity); a 240-second
client rotation also rechecks authentication. Browser `online` wakes a retry early.
Unsubscribing aborts the active connection and cancels retry timers.

Every connection uses the existing authenticated HTTP client. An expired access
token can refresh through the HttpOnly cookie flow. Terminal 401/403/404 errors
are not retried forever. Transient network/5xx/rate-limit errors show a quiet
reconnecting status, not a global error banner. Processing-document polling
continues every two seconds and suppresses transient background errors; upload,
retry and explicit question errors still use their normal error feedback.

After connecting, the client reloads document metadata and reconciles known
statuses using attempt IDs and timestamps. This recovers missed status messages
without treating old snapshots as newer events. The SSE reader accepts LF/CRLF
boundaries, split UTF-8 characters and comment heartbeats and releases its reader
on errors. Generation requests are never automatically resubmitted as part of
this document-stream retry mechanism.

## Deployment

Deploy both backend and frontend branches. No migration is needed. If Nginx is
used, apply the SSE locations in `deploy/nginx/askmemind.conf.example` to the
actual API virtual host, preserving its TLS/origin configuration. Run `nginx -t`
before reloading. In particular: buffering/cache/gzip off, HTTP/1.1, empty
Connection header, and proxy_read_timeout 300s. Adjust route prefixes if the
proxy exposes the API under `/api`. Do not proxy to the Vite development server
or put access tokens in query strings.

CDNs/load balancers can still enforce their own maximum connection lifetime;
periodic disconnect/reconnect is expected. A persistent reconnecting state means
the API/proxy/Redis path needs inspection, not that the browser should keep an
unbounded number of open streams. These changes do not diagnose the exact timeout
configured on an external VPS or CDN without its logs.
