# Security

This document describes the security controls implemented in this project,
known limitations, and how to keep dependencies up to date.

## Authentication & Session Security

- **Password hashing**: bcrypt (backend/app/core/security.py).
- **Login rate limiting**: `POST /auth/login`, `POST /auth/refresh`,
  `POST /auth/forgot-password` and `POST /auth/reset-password` are
  rate-limited per client IP and per endpoint (`RATE_LIMIT_LOGIN_ATTEMPTS` per
  `RATE_LIMIT_LOGIN_WINDOW_SECONDS`, see `app/config.py`). Implemented as an
  in-memory, single-process fixed-window counter
  (`app/core/rate_limit.py`).
  - **Client IP behind a proxy**: by default the TCP peer address is used, so
    behind a reverse proxy (e.g. Render) every user shares one bucket. Set
    `TRUSTED_PROXY_COUNT` to the number of proxies that append to
    `X-Forwarded-For`; the client is then the Nth entry from the *right* (the
    part your own proxy wrote, never the client-controlled left side). Verify
    the value against a real request's headers before relying on it.
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

### Request body size limits

`app/core/body_limit.py` is an ASGI middleware that rejects oversized request
bodies with `413 {"detail": "Request body too large."}` **before** any parser or
authentication runs (FastAPI parses the body first), independent of the hosting
platform. The limit depends on the request:

| Request | Limit (setting) | Default |
|---|---|---|
| `multipart/form-data` on exactly the two upload routes | endpoint per-file cap (`MAX_UPLOAD_SIZE_MB` / `MAX_RESUME_UPLOAD_SIZE_MB`) + 1 MiB framing | 50 MB / 5 MB |
| `application/x-www-form-urlencoded` (anywhere; only login uses it) | `MAX_FORM_BODY_KB` | 16 KiB |
| anything else (JSON, multipart elsewhere, …) | `MAX_REQUEST_BODY_KB` | 256 KiB |

- A declared `Content-Length` over the limit is rejected without reading the body;
  without one (chunked), bytes are counted as they are read and reading stops with
  413 one chunk past the limit — an oversized body is never held in memory.
- The upload allowance is route- *and* content-type-specific: a multipart body to
  any other endpoint, or a urlencoded body to an upload route, gets the small limit.
  A test fails if a route that accepts a file is not registered in `UPLOAD_ROUTES`.
- Endpoints still enforce their exact per-file limits and messages.
- Defaults are chosen from measurement, not guesswork: the largest legitimate body
  is ~41 KB (session with a maximum-length description in 4-byte characters); the
  login form is ~170 bytes; parsing a urlencoded body of tiny fields costs ~0.1 s at
  16 KiB but ~17 s of event-loop time at 1 MiB.
- Rejected requests are not counted by the login rate limiter (they never reach it);
  they are cheap (no body read), and rejected/streamed cases are logged at WARNING.

## Logging & Audit

Security-relevant events are logged via a dedicated `"app.security"` logger
(`app/core/security_logging.py`): failed logins, account lockouts,
successful logins, rate-limit rejections, token refreshes/rejections,
logouts, and upload rejections. These log lines never include passwords,
raw tokens/secrets, or email addresses — only user IDs (UUIDs), client IPs,
and fixed reason codes, so they are safe to ship to a SIEM or centralized
log store without handling them as PII.

## Dependency Security

Dependency audits are a **blocking CI gate** (`.github/workflows/security.yml`),
run on every push and pull request and weekly (Mondays 04:17 UTC — new
advisories are published against code that has not changed). A production
dependency with an advisory that is not documented below fails the run.

| Gate | Covers | Command (local = CI) |
|---|---|---|
| Python | `backend/requirements.txt` (runtime) **and its transitive dependencies**, exactly as `pip install` resolves them | `cd backend && pip install pip-audit==2.7.3 && python scripts/audit_dependencies.py` |
| JavaScript | production dependency tree of `frontend/` (`npm ci` lockfile) | `cd frontend && npm ci && npm run audit` |

Both gates are **fail-closed**:

- Any advisory not listed in the exceptions file fails the run, at any severity
  (there is no severity threshold that could hide a finding).
- Python runs `pip-audit --strict`: a package that cannot be audited fails the
  run instead of being skipped. The runner audits `torch==X` when the pin is the
  CPU wheel `torch==X+cpu` (that local version is not on PyPI and would
  otherwise be silently unaudited — it is the same upstream release).
- Node fails on an unreachable registry or unparseable `npm audit` output, and
  does not trust `npm audit`'s own exit code — the verdict comes from the
  advisories themselves.
- No step uses `|| true`; `tests/test_ci_config.py` fails if a job-level
  `continue-on-error` or an exit-code-swallowing command is introduced.

### Runtime vs dev dependencies

`backend/requirements.txt` is what the Docker image ships and what the gate
audits. Test/lint/audit tooling (`pytest`, `black`, `ruff`, `pip-audit`, …) lives
in `backend/requirements-dev.txt` (which starts with `-r requirements.txt`).
Advisories in dev tooling — and in `frontend` devDependencies — are **reported
but never block**, by one explicit, named "informational" step per job; they are
not shipped to users. Install for development with
`pip install -r requirements-dev.txt`.

### Documented exceptions

An exception is a specific advisory ID, never a whole package, and must state
what the affected feature is, why it is not blocking, and a **"Remove when"**
condition. The full text is next to the IDs:
[`backend/pip-audit-exceptions.txt`](backend/pip-audit-exceptions.txt) and
[`frontend/audit-exceptions.json`](frontend/audit-exceptions.json); shape is
enforced by tests. Baseline triaged 2026-09-21:

| Package | Advisories | Why it does not block today | Remove when |
|---|---|---|---|
| `torch` 2.6.0 | 22 | App never calls torch APIs directly (no compile/JIT/`torch.load` of user data); used only via Whisper (fixed checkpoint, SHA-256 checked, `weights_only`) and sentence-transformers. Patched releases exist (2.7–2.13) but need the ML pipeline re-tested. | torch upgraded to a patched release |
| `transformers` 4.57.6 | 5 | Advisories are in training / conversion / `trust_remote_code` / `save_pretrained`; the app only runs inference on one fixed hub model. Fixes are 5.x (major). | transformers ≥ 5.10 compatible with sentence-transformers/whisper |
| `protobuf` 4.25.9 | 1 | `ParseDict` DoS; never called. Pulled in only by the OpenTelemetry exporter, which caps protobuf < 5. | OpenTelemetry upgraded to allow protobuf 5+ |
| `ecdsa` 0.19.2 | 1 | Timing attack on ECDSA *signing*; the app signs HS256 only. No upstream fix exists. | python-jose drops/replaces ecdsa, or a fix ships |
| `starlette` 0.47.3 | 6 | **One applies but is mitigated:** urlencoded body limits are ignored (login form) — fix only in starlette 1.3.1 (major); **compensating control:** the request-body limit above caps urlencoded bodies at 16 KiB before Starlette parses them (worst case ~0.1 s instead of ~17 s at 1 MiB). The advisory stays listed because the vulnerable Starlette code is still present. Five do not: `FileResponse` (fixed in 0.49.1, which needs fastapi ≥ 0.120.1 and therefore crosses FastAPI 0.118's change to `yield`-dependency cleanup timing — validate that first), `StaticFiles`, `HTTPEndpoint`, `request.url` host reconstruction. The multipart-upload advisory (PYSEC-2026-1941) that used to be listed here is **resolved** (fastapi 0.116.1 + starlette 0.47.3). | starlette ≥ 1.3.1 via a compatible FastAPI (urlencoded, `request.url`, `StaticFiles`, `HTTPEndpoint`); fastapi ≥ 0.120.1 (`FileResponse`) |
| `react-router` 6.30.x | 2 | Open redirect needs an attacker-controlled navigation target (every target in `src/` is a literal, fixed prefix + id, or static map); the SSR-hydration issue does not apply to a client-only SPA. Fix is v7 only. | migrate to react-router 7.18+ |

### When the gate goes red

1. Read the advisory (`pip-audit` / `npm audit` output names the fixed version).
2. **Prefer fixing it:** bump the smallest version that resolves it, re-run the
   full test suite. Do not cross a major version merely to silence an audit.
3. If there is genuinely no compatible fix or the vulnerable feature is
   verifiably unused, add the ID to the exceptions file with the category, the
   reason and the "Remove when" condition. Never add an ID only to get CI green.
4. When an upgrade lands, delete the exceptions it makes obsolete (the Node
   runner warns about exceptions that are no longer reported).

### Known limits

- **A blocking audit can fail a PR that touched no dependencies**, because new
  advisories appear against unchanged versions and transitive dependencies are
  resolved at audit time. That is the point of the gate; triage per the steps
  above (the weekly run surfaces it before an unrelated PR does).
- The Python audit resolves dependencies for the platform it runs on. CI runs on
  Linux; local runs on Windows/macOS can resolve slightly different sets.
- The gate blocks a *merge* only if the `Security` workflow's jobs are set as
  **required status checks** in the repository's branch-protection settings
  (a GitHub setting, not something the repo can enforce itself).
- The `secrets-scan` (gitleaks) job is still informational.
- Re-run the full test suite (`pytest` / `npm run test`) after any dependency bump.
