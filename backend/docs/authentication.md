# Authentication and Persistent Browser Sessions

## Browser Contract

Browser authentication uses a short-lived access token in JSON and an opaque refresh token in a persistent **HttpOnly cookie**. JavaScript never receives the refresh token in a response body. Access tokens still use `Authorization: Bearer <access_token>`; cookies alone do not authenticate `/auth/me`, document or chat endpoints.

Use `credentials: 'include'` for login, refresh and logout. Those three POST endpoints also require:

- An `Origin` exactly matching `AUTH_CSRF_TRUSTED_ORIGINS`. Browsers set this header automatically; JavaScript must not try to override it.
- The custom header `X-CSRF-Protection: 1`.

There is no Referer fallback, wildcard/suffix matching or missing/null Origin exemption. The custom header forces preflight for cross-origin requests and prevents simple HTML forms from invoking these endpoints. It is a fixed AJAX marker, not a session secret; exact Origin checking and explicit credentialed CORS are part of this protection. SameSite is defense in depth. CSRF failures return `403` before session mutation and do not set/delete cookies.

All `/auth/` responses use `Cache-Control: no-store` and `Pragma: no-cache`. Never log Authorization, Cookie, Set-Cookie, credential-bearing request bodies or token values in API/proxy/analytics/error-reporting layers.

## Browser Endpoints

| Endpoint | Request | Success |
|---|---|---|
| `POST /auth/register` | JSON email/password | `201` UserRead; no cookie/session |
| `POST /auth/login` | JSON email/password, Origin and CSRF header | `200` access-only JSON plus Set-Cookie |
| `POST /auth/refresh` | Cookie, Origin and CSRF header; no JSON or bearer needed | `200` access-only JSON plus rotated Set-Cookie |
| `POST /auth/logout` | Cookie, current bearer, Origin and CSRF header; no JSON needed | `204`, refresh revoked, access blacklisted, cookie deleted |
| `GET /auth/me` | Bearer access token | `200` UserRead |

Login input:

```json
{"email":"user@example.com","password":"your-password"}
```

Login/refresh JSON response (no refresh token):

```json
{"access_token":"<jwt>","token_type":"bearer"}
```

Production Set-Cookie defaults resemble:

```http
Set-Cookie: __Host-askmemind_refresh=<opaque>; Path=/; HttpOnly; Secure; SameSite=lax; Max-Age=<remaining-seconds>; Expires=<absolute-GMT-expiry>
```

No Domain attribute is set: the cookie belongs only to the API host. The `__Host-` prefix requires Secure and Path=/ and protects against sibling-domain cookie injection. The root path is intentional for this prefix; the token is nevertheless read only by browser auth endpoints.

On reload or reopening the browser, POST `/auth/refresh` with credentials and the CSRF header, keep the returned access token in RAM, then call `/auth/me`. Max-Age and Expires allow the cookie to survive browser closure until the original session expires; privacy settings/private browsing/manually clearing cookies can still remove it. Browser JavaScript cannot read HttpOnly cookies or the Set-Cookie response header. Neither token belongs in localStorage/sessionStorage.

Refresh reads **only the cookie**; JSON refresh tokens are never a fallback. Replacement rows retain the original `expires_at`, and cookie lifetime decreases rather than restarting the session duration. Token issuance snapshots the account version while holding the user lock, before commit releases it.

Serialize refresh requests, including across tabs. Concurrent uses of one rotated token are replay and revoke all refresh sessions for that user. A per-tab promise is insufficient for simultaneous tabs; the frontend should coordinate using Web Locks/BroadcastChannel or another cross-tab mechanism. Do not automatically retry refresh after an ambiguous network failure: the server may have consumed the token. Strict replay detection is retained without a grace window.

### Errors and Logout

- Login: incorrect credentials/inactive user `401`; invalid body `422`.
- Refresh: missing/malformed/unknown/expired/revoked cookie `401`, deleting the cookie with matching attributes.
- Logout: invalid/missing refresh cookie or ownership mismatch `401` and cookie deletion, without revoking another user's session. A currently valid bearer token is required; invalid access returns `401` through the dependency. If access expired, refresh once before logout.
- All three browser POST endpoints: untrusted/missing/null Origin or missing/incorrect CSRF header `403`, no session mutation or cookie changes.
- Redis errors: `503`. On logout, if blacklist writing fails after refresh revocation, retain the cookie so logout can be retried with the still-valid access token. Do not treat `503` as completed logout.
- Registration: duplicate email `400`; registration disabled `403`; invalid fields `422`.

Successful logout revokes the submitted refresh token, blacklists the presented access jti, deletes the cookie with the same name/path/HttpOnly/Secure/SameSite attributes and returns no body. The client clears its in-memory access token. In-flight requests/open SSE connections are not interrupted; revocation applies on subsequent authenticated requests.

### Frontend Integration Examples

These are contract examples, not changes to React:

```javascript
const API = 'https://askmemind-backend.fullfact.xyz';
const loginResponse = await fetch(`${API}/auth/login`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Protection': '1' },
  body: JSON.stringify({ email, password }),
});
// Check response.ok before consuming or using a token.
const refreshResponse = await fetch(`${API}/auth/refresh`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'X-CSRF-Protection': '1' },
});
// On 200 keep access_token in memory; on 401 show sign-in.
await fetch(`${API}/auth/logout`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'X-CSRF-Protection': '1', Authorization: `Bearer ${accessToken}` },
});
```

Frontend integration must check response status, handle errors and serialize refresh. Protected requests still send the bearer header. Native EventSource cannot attach it; retain fetch-based SSE with the current access token. Existing React/CLI clients must migrate to this new contract before deployment; this backend task does not change them.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `production` | `production` or `local`; production refuses insecure refresh cookies |
| `AUTH_REFRESH_COOKIE_NAME` | `__Host-askmemind_refresh` | Name; change for HTTP localhost |
| `AUTH_REFRESH_COOKIE_PATH` | `/` | Used for both setting/deletion; `__Host-` requires `/` |
| `AUTH_REFRESH_COOKIE_SECURE` | `True` | HTTPS-only; can be False only in local mode |
| `AUTH_REFRESH_COOKIE_SAMESITE` | `lax` | lax/strict/none; none requires Secure |
| `AUTH_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated exact frontend origins; empty blocks browser auth POSTs |
| `BACKEND_CORS_ORIGINS` | empty | Explicit origins for credentialed CORS; empty disables cross-origin access |
| `AUTH_JSON_TOKENS_ENABLED` | `False` | Opt in to isolated CLI/native body-token endpoints |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Absolute lifetime assigned only on login |

Origin lists reject `*`, wildcard subdomains, `null`, credentials, paths, queries, fragments and trailing slashes. Use exact frontend scheme/hostname/port. CORS and CSRF lists are independent: CORS alone never authorizes cookie operations. CORS allows credentials and explicit methods/headers, including the CSRF header; no wildcard origins, methods or headers are configured.

Swagger `/docs` runs at the API origin. To test browser login/refresh/logout there, explicitly allow that API origin in the CSRF list and send the CSRF header. It is not implicitly trusted because it matches Host. CLI smoke requests must deliberately supply the configured browser Origin/CSRF header and retain the cookie, or use the opt-in native endpoints.

### HTTP Localhost

```ini
ENVIRONMENT=local
AUTH_REFRESH_COOKIE_NAME=askmemind_refresh
AUTH_REFRESH_COOKIE_PATH=/
AUTH_REFRESH_COOKIE_SECURE=False
AUTH_REFRESH_COOKIE_SAMESITE=lax
AUTH_CSRF_TRUSTED_ORIGINS=http://localhost:5173
BACKEND_CORS_ORIGINS=http://localhost:5173
AUTH_JSON_TOKENS_ENABLED=False
PASSWORD_RESET_URL=http://localhost:5173/reset-password
```

Use localhost for both frontend and API, or 127.0.0.1 for both; they are different sites. If using Vite's `/api` proxy, the browser Origin remains the frontend origin and the proxy must forward Cookie/Set-Cookie. Cookies are not port-isolated, so avoid unrelated localhost apps sharing the same cookie name.

### Production Custom Domains

```ini
ENVIRONMENT=production
AUTH_REFRESH_COOKIE_NAME=__Host-askmemind_refresh
AUTH_REFRESH_COOKIE_PATH=/
AUTH_REFRESH_COOKIE_SECURE=True
AUTH_REFRESH_COOKIE_SAMESITE=lax
AUTH_CSRF_TRUSTED_ORIGINS=https://askmemind.fullfact.xyz
BACKEND_CORS_ORIGINS=https://askmemind.fullfact.xyz
AUTH_JSON_TOKENS_ENABLED=False
PASSWORD_RESET_URL=https://askmemind.fullfact.xyz/reset-password
```

Load configuration into both API and Celery workers. Cookie name/host/path changes do not delete old cookies: deliberately expire any legacy cookie using its original attributes when migrating such settings. No DB migration is needed for this transport change; previous auth migrations must already be applied.

## Vercel and API Domains

Recommended: keep Vercel hosting but attach `askmemind.fullfact.xyz`; expose the API at `askmemind-backend.fullfact.xyz`. HTTPS and the shared registrable site `fullfact.xyz` let Lax cookies work without depending on third-party cookies. They are still different origins, so explicit CORS and credentials:include remain necessary. Keep the cookie host-only, without Domain=.fullfact.xyz.

Alternatively, reverse-proxy `/api/*` from the frontend's own origin to the API. Preserve Origin, Cookie/Set-Cookie, Authorization and the CSRF header; do not weaken Secure/HttpOnly/SameSite or alter expiry. The root cookie path works when stripping `/api`; a narrower local cookie path must match the browser-visible URL. Preserve SSE streaming. Origin validation never trusts Host/X-Forwarded-Host to build an allowlist.

Avoid `project.vercel.app` calling an unrelated API site directly. That requires cross-site cookies: SameSite=None plus Secure is configurable, but browser third-party cookie blocking can still break persistence. Use a shared-site custom domain or same-origin proxy instead. Preview deployments need explicitly trusted origins and compatible site/proxy setup; never wildcard *.vercel.app.

## Optional CLI / Native Flow

Enable `AUTH_JSON_TOKENS_ENABLED=True` only when another client needs body tokens:

| Endpoint | Input | Success |
|---|---|---|
| `POST /auth/token/login` | JSON email/password | `200` access_token, refresh_token, token_type |
| `POST /auth/token/refresh` | `{"refresh_token":"<current-token>"}` | `200` rotated pair |
| `POST /auth/token/logout` | Same refresh JSON plus bearer header | `204` |

They never read/set cookies. Any Origin, Sec-Fetch-Site or Cookie header returns `403`, including trusted browser origins. This cannot serve as a React CSRF escape route. Disabled endpoints return `404` for valid requests; invalid tokens return `401` and invalid fields `422`. Services preserve identical rotation, absolute expiry, replay and revocation behavior.

Existing CLI/Streamlit integrations using /auth/login must explicitly migrate and opt in. There is no fallback based on missing Origin, a body token, query parameter or User-Agent. Browser refresh tokens previously held in JavaScript should be discarded; sign in once through cookie login to establish the new session transport.

## Preserved Revocation and Password Recovery

JWTs retain sub/jti/iat/exp/ver with signature/claim validation. Passwords use Argon2. Opaque refresh tokens contain 256 bits of randomness; PostgreSQL stores SHA-256 digests only. User locks serialize login, rotation, logout and password reset. Rotation inserts/links the successor and revokes its predecessor atomically. Reusing a non-expired revoked token revokes all refresh sessions for that user. Expired replay cannot revoke newer logins. Refresh replay does not revoke already-issued access tokens; their existing lifetime is unchanged.

Logout blacklists the access jti until expiry. Redis errors fail closed. Keep Redis private/persistent (Compose uses AOF), without eviction or flushing auth keys; losing a blacklist key can permit a logged-out JWT until expiry. Password reset increments the DB account version, so that revocation survives Redis loss.

Successful reset atomically updates the password, increments token_version, consumes all reset links and revokes all refresh tokens. Old access tokens fail on the next request, old cookies fail and are deleted on refresh. Reset never creates a new session.

`POST /auth/forgot-password` accepts JSON email and returns generic `202` for known/unknown accounts. Account lookup/token generation occur in the worker; only email/request ID travel through the broker. Missing email configuration or enqueue failure returns generic `503`; logs contain flags/error types, not secrets. SMTP delivery failures occur later in the worker. Limits: three messages/email/hour (extra attempts return generic 202 without queuing), ten attempts/IP/hour (429).

`POST /auth/reset-password` accepts `{"token":"<emailed-token>","new_password":"new-password"}`. It returns `204`, `400` for invalid/expired/used tokens, `422` for invalid password length (8-128), `429` for more than ten attempts/IP/minute and `503` on Redis failure. Recovery endpoints never authenticate through refresh cookies; reset requires the separate email token.

SMTP configuration in both API/worker environments:

```ini
PASSWORD_RESET_EXPIRE_MINUTES=15
PASSWORD_RESET_URL=https://askmemind.fullfact.xyz/reset-password
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=auth@example.com
SMTP_USE_SSL=False
```

Port 587 uses mandatory STARTTLS; implicit TLS uses SMTP_USE_SSL=True with the provider's port (usually 465). Certificates are verified. Reset URLs require HTTPS except localhost/127.0.0.1; links use #token=..., consumed/removed by the frontend before analytics. The worker owns/closes its DB session and retries delivery failures three times with generic errors. New reset issuance invalidates older links. SMTP and DB cannot commit together: after partial delivery/retry, use the newest link. Keep revoked refresh rows until their original expiry when scheduling retention cleanup.

## Verification and References

On isolated PostgreSQL/pgvector, run migrations then `python -m pytest tests -q` from backend. AUTH_TEST_REDIS_URL enables real Redis checks. Tests cover cookie flags/persistence, absolute expiry, rotation/replay, deletion/ownership, missing/expired/invalid cookies, reset revocation, CSRF, native separation, explicit credentialed CORS, concurrency and rollback. SMTP is mocked; tests do not email production users.

References: [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie), [RFC 9700 rotation](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).
