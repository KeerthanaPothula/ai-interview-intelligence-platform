# Security

This document describes the security controls implemented in this project,
known limitations, and how to keep dependencies up to date.

## Authentication & Session Security

- **Password hashing**: bcrypt (backend/app/core/security.py).
- **Login rate limiting**: `POST /auth/login` and `POST /auth/refresh` are
  rate-limited per client IP (`RATE_LIMIT_LOGIN_ATTEMPTS` per
  `RATE_LIMIT_LOGIN_WINDOW_SECONDS`, see `app/config.py`). Implemented as an
  in-memory, single-process fixed-window counter
  (`app/core/rate_limit.py`).
  - **Known limitation**: state is not shared across multiple
    Uvicorn/Gunicorn workers or horizontally scaled instances, and does not
    survive a process restart. This project has no Redis (or other shared
    cache) infrastructure; adding one solely for rate limiting was judged a
    disproportionate change for the current single-worker deployment.
  - **Upgrade path**: replace `InMemoryRateLimiter` with a Redis-backed
    limiter using `INCR` + `EXPIRE` on the same `"{path}:{ip}"` key scheme —
    the `enforce_login_rate_limit` dependency's interface does not need to
    change.
- **Account lockout**: after `ACCOUNT_LOCKOUT_THRESHOLD` consecutive failed
  password attempts against one account, that account is locked for
  `ACCOUNT_LOCKOUT_DURATION_MINUTES`, doubling on each subsequent lockout
  (progressive backoff) up to `ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES`
  (`app/services/auth_service.py`).
  - **Accepted trade-off**: an HTTP 423 ("account locked") response is only
    returned for accounts that exist, which reveals account existence to an
    attacker who has already triggered a lockout. Ordinary failed logins
    (wrong password, unknown email) remain indistinguishable (generic 401).
    This is the standard OWASP-accepted trade-off for brute-force
    protection — the alternative (returning a generic 401 even when locked)
    would let an attacker keep retrying indefinitely without ever being
    told to stop.
- **JWT access tokens**: short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`),
  carry a `"ver"` claim checked against `User.token_version`
  (`app/core/deps.py`). Bumping `token_version` instantly invalidates every
  previously issued access token for that user without needing a
  blacklist store — the mechanism chosen over a separate revoked-token
  table for its simplicity. Tokens issued before this feature shipped have
  no `"ver"` claim and are treated as version `0`, matching the column
  default, so they remain valid (no forced logout on deploy).
- **Refresh tokens**: long-lived (`REFRESH_TOKEN_EXPIRE_DAYS`), stored only
  as SHA-256 hashes (`refresh_tokens.token_hash`), never in plaintext.
  Redeeming a refresh token (`POST /auth/refresh`) rotates it: the
  submitted token is revoked and a new one is issued in the same call, so
  each refresh token can only ever be used once. Replaying an
  already-revoked token revokes every other active refresh token for that
  user, as a defensive response to suspected token theft.
  `POST /auth/logout` revokes one refresh token; it does not invalidate the
  caller's current access token (that token remains valid until it expires
  naturally). Logging out of all devices/sessions immediately requires
  bumping `token_version`, which is not exposed via an endpoint yet.

## Cross-Site Request Forgery (CSRF)

No CSRF middleware/token is implemented, and this is a deliberate
assessment, not an oversight:

- The API is authenticated exclusively via a Bearer token in the
  `Authorization` header (`app/core/deps.py::get_current_user`), read from
  JavaScript-managed storage (`localStorage`, `AuthContext.tsx`) — never a
  cookie.
- CSRF is fundamentally an attack on **ambient authority**: a browser
  automatically attaching a cookie to a cross-origin request the victim
  didn't intend to make. A cross-site page cannot read `localStorage`
  belonging to another origin, and cannot set a custom `Authorization`
  header on a simple cross-origin form/image/script request — so it
  cannot forge an authenticated request to this API. The CORS
  configuration (`CORS_ORIGINS` allow-list, `app/main.py`) additionally
  blocks a cross-origin script from reading the response even if it could
  make the request.
- **This would need revisiting** if the token storage strategy ever moves
  to cookies (e.g. to mitigate XSS token theft via `httpOnly` cookies) —
  that trade-off swaps one risk (XSS-readable token) for another (CSRF
  exposure) and would require adding real CSRF protection (double-submit
  token or `SameSite=Strict`) at the same time.

## Security Headers

`SecurityHeadersMiddleware` (`app/core/security_headers.py`) sets
Content-Security-Policy, X-Frame-Options, X-Content-Type-Options,
Referrer-Policy, and Permissions-Policy on every response.
Strict-Transport-Security is only sent when `ENVIRONMENT=production`, since
HSTS over plain HTTP in local development is meaningless and can cause
browsers to refuse subsequent plain-HTTP connections to `localhost`.

## File Upload Validation

Both audio responses (`app/services/upload_service.py`) and resume uploads
(`app/routers/documents.py`) apply layered validation, in order:

1. Declared MIME type / file extension against an allow-list (HTTP 415).
2. File size against a configured ceiling (HTTP 413).
3. Magic-byte (file-signature) check that the file's actual leading bytes
   match the declared MIME type (`app/core/file_validation.py`, HTTP 422) —
   this catches a payload that spoofs its `Content-Type` header.
4. A malware-scan hook (`scan_for_malware`) — **currently a stub that
   always returns `True`**. This is the integration point for a real
   scanner (e.g. ClamAV via a `clamd` socket, or a cloud scanning API)
   before accepting uploads in any deployment that needs malware
   protection.
5. Filename sanitization (`sanitize_filename`) strips directory components
   and unsafe characters before a client-supplied filename is persisted for
   display. Files are always written to disk under a server-generated
   UUID name, never the client-supplied name, so this is defense-in-depth
   rather than the primary path-traversal control.

## Input Validation

Request schemas (`app/schemas/*.py`) bound free-text fields that are sent to
Gemini or stored, to prevent unbounded payloads from inflating AI token
usage or storage: job descriptions, live-interview response text, and the
RAG-generated question count are all capped.

## Logging & Audit

Security-relevant events are logged via a dedicated `"app.security"` logger
(`app/core/security_logging.py`): failed logins, account lockouts,
successful logins, rate-limit rejections, token refreshes/rejections,
logouts, and upload rejections. These log lines never include passwords,
raw tokens/secrets, or email addresses — only user IDs (UUIDs), client IPs,
and fixed reason codes, so they are safe to ship to a SIEM or centralized
log store without handling them as PII.

## Dependency Security

### Python (backend)

```bash
cd backend
pip install pip-audit  # already in requirements.txt as a dev dependency
pip-audit -r requirements.txt
```

Review any reported advisories and bump the affected pin in
`requirements.txt`. Re-run the backend test suite after any version bump.

### JavaScript (frontend)

```bash
cd frontend
npm audit --omit=dev   # npm run audit
```

Use `npm audit fix` for non-breaking fixes; review breaking fixes manually
before applying.

### General guidance

- Run both audits before each release and periodically (e.g. monthly) even
  without a release pending — new advisories are published against
  already-pinned versions.
- Prefer the smallest version bump that resolves an advisory rather than
  jumping to the latest major version, to limit unrelated behavior changes.
- Re-run the full test suite (`pytest` / `npm run test`) after any
  dependency bump before merging.
