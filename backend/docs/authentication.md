# Authentication and Token Lifecycle

## Implemented Lessons

1. Access tokens contain `sub` (user ID), `jti` (unique token ID), `iat` (issued-at), `exp` (expiry), and `ver` (account token version).
2. Decoding verifies the signature, expiry, issue time, required identifiers and integer timestamps. `AccessTokenPayload` exposes the validated data. Tokens issued before account versioning default to version zero.
3. `refresh_tokens` stores SHA-256 digests of 256-bit opaque tokens, user IDs, expiration, revocation and replacement IDs. Raw tokens are returned once and never stored in the DB.
4. Login locks the user row, checks the current password and active state, saves a refresh-token digest and returns both tokens.
5. Refresh locks the user then token, replaces the token and revokes its predecessor in one transaction. Absolute expiry is preserved. Reusing a revoked token revokes **all refresh sessions** for the user, including other devices. This conservative policy does not require a family column; clients must serialize refresh requests and persist the new token before the next refresh. A lost refresh response requires signing in again.
6. Logout requires a valid bearer access token and a refresh token belonging to the same user. It revokes the submitted refresh token and blacklists the submitted access token. It does not log out other devices. An already-revoked access token receives `401` on subsequent requests.
7. Redis keys `auth:revoked:<jti>` live until access-token expiration. Redis errors fail closed with `503`; they never silently authorize a request. The user record is also checked on each protected request, so disabled users cannot authenticate.
8. Password-reset tokens are opaque, hashed in the DB, expiring and single use. A successful reset updates the password hash, increments the account token version, consumes all reset links and revokes all refresh tokens in one transaction. Other access tokens fail on their next request, including tokens created in the same second as the reset. Existing open streams are not interrupted mid-request.

User-row locks serialize login, rotation, logout, reset-link creation and password reset. Concurrent uses of the same refresh or reset token cannot both succeed. Repositories roll back failed multi-write transactions.

## API Payloads

`POST /auth/login`:

```json
{"email": "user@example.com", "password": "your-password"}
```

Login and `POST /auth/refresh` return:

```json
{"access_token": "<jwt>", "refresh_token": "<opaque-token>", "token_type": "bearer"}
```

Send `Authorization: Bearer <access_token>` on protected requests. All `/auth/` responses have `Cache-Control: no-store`.

`POST /auth/refresh` accepts `{"refresh_token": "<current-refresh-token>"}` and returns a new pair. Invalid, expired or reused tokens return `401`. Existing access tokens keep their remaining lifetime after rotation or refresh replay; refresh replay revokes refresh sessions only.

`POST /auth/logout` accepts the same JSON body plus the bearer header and returns `204`. The client must discard both tokens. If Redis fails after refresh revocation, logout returns `503`; the refresh token is already revoked and the access blacklist write can be retried while that access token is valid.

`POST /auth/forgot-password` accepts `{"email": "user@example.com"}` and returns `202` with a generic message. Both known and unknown emails are queued; account lookup happens in the worker. An account can request up to three messages per hour; requests over that email limit receive the same generic `202` without queuing more mail. Each source IP is limited to ten requests per hour (`429`). Missing email configuration or a failed broker publish returns `503` for all emails.

`POST /auth/reset-password` accepts:

```json
{"token": "<token-from-email>", "new_password": "your-new-password"}
```

Success returns `204`, invalid/expired/consumed tokens return `400`, and invalid password length returns `422`. Passwords must be 8-128 characters. Reset attempts are limited to ten per IP per minute (`429`). Reset does not automatically log the user in.

## Email and Deployment

Run `alembic upgrade head` from `backend` before starting the updated API and worker. Migration `8a7d32e901bc` adds `password_reset_tokens` and `users.token_version`.

Configure these variables in **both API and Celery worker** environments:

```ini
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30
PASSWORD_RESET_EXPIRE_MINUTES=15
PASSWORD_RESET_URL=https://your-frontend.example/reset-password
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=auth@example.com
SMTP_USE_SSL=False
```

Port 587 uses mandatory STARTTLS. For implicit TLS use `SMTP_USE_SSL=True` and the provider's TLS port, usually 465. Certificate verification is enabled. The configured reset URL must use HTTPS except for local development on `localhost` or `127.0.0.1`; it is never taken from an incoming Host header.

The worker handles `auth.send_password_reset` using its own DB session, closes it in `finally`, and retries delivery failures up to three times. Each new issuance invalidates previous reset links. A retry after partial SMTP delivery may therefore invalidate an earlier email; use the newest link. Worker logs record error types and request IDs, not raw tokens or SMTP message content. Only the email and request ID travel through the Celery broker; the reset token is generated in the worker.

Email links look like `https://your-frontend.example/reset-password#token=...`. The frontend must read `window.location.hash`, remove it with `history.replaceState`, collect a new password and POST the token in the JSON body. **This backend change does not add a React reset page or automatic refresh handling.** Configure the URL to a page that implements that flow before enabling email recovery.

Protect tokens with HTTPS, avoid logs/analytics containing token values, and do not persist bearer tokens in browser localStorage. The current API returns refresh tokens in JSON for explicit clients; a browser deployment can add Secure HttpOnly refresh cookies together with CSRF protection as a separate client/API change. Apply login/register rate limits at the gateway as well; the built-in limits here cover password recovery. Configure trusted proxy forwarding so rate limits see the actual client IP; never trust arbitrary X-Forwarded-For headers from the public internet.

Redis is now required for authenticated traffic and recovery rate limits. Keep Redis private, use persistence (Compose enables AOF), and avoid eviction or flushing auth keys: losing a blacklist key permits a logged-out access token until its JWT expires. Keep broker/result cleanup away from auth keys. Short access lifetimes bound this risk. Account token versions make password-reset revocation durable in PostgreSQL even if Redis restarts.

Expired/consumed DB token rows are retained for replay detection and audit. Schedule a retention cleanup that preserves revoked refresh rows until their original expiry. SMTP delivery and the DB cannot commit atomically; monitor email-failure events, and users can request another link after a delivery failure.

## Verification

Run migrations on an isolated PostgreSQL/pgvector test DB, then `python -m pytest tests -q` from `backend`. Set `AUTH_TEST_REDIS_URL` to an isolated Redis to include real blacklist and Lua rate-limit checks; CI configures PostgreSQL and Redis. Tests also cover token validation, rotation replay, concurrent rotation/reset, logout ownership, Redis outages, one-use password reset, session invalidation, generic recovery responses and mocked SMTP/worker failures. SMTP credentials and real inbox delivery are deployment checks.

Design references: [RFC 9700 refresh-token rotation](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14) and [OWASP password recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).
