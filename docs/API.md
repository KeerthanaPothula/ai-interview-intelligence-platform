# API Reference

Base URL: `http://localhost:8000` locally, or your deployed backend origin.
Interactive docs (Swagger UI at `/docs`, ReDoc at `/redoc`) are generated
automatically by FastAPI from the same Pydantic schemas documented here, and
are available whenever `DEBUG=true`.

## Authentication

All routes except `/health`, `/ready`, `/metrics`,
`POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and
`POST /api/v1/auth/refresh` require:

```
Authorization: Bearer <access_token>
```

Access tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 1440
minutes). Use `POST /api/v1/auth/refresh` with a refresh token to obtain a
new access/refresh pair without re-authenticating with a password. Every
response schema below omits internal fields (password hashes, raw file
paths) by construction — these are never serialized to the client.

**Ownership rule**: every resource scoped to a user (sessions, questions,
responses, documents, live interviews) is filtered by the authenticated
user's ID at the query level. A resource that exists but belongs to another
user returns `404`, identical to a resource that doesn't exist — this
prevents account enumeration. See [SECURITY.md](../SECURITY.md).

---

## Health & Observability

### `GET /health`

Liveness check. Never touches the database. Always returns `200` while the
process is up.

```json
{
  "status": "healthy",
  "environment": "production",
  "version": "1.0.0",
  "audio_processing_enabled": true
}
```

### `GET /ready`

Readiness check — confirms the database is reachable
(bounded by `READINESS_DB_TIMEOUT_SECONDS`) and that an AI provider key is
configured. Returns `503` if either check fails.

```json
// 200 OK
{
  "status": "ready",
  "checks": {
    "database": { "ok": true, "error": null },
    "ai_provider_configured": { "ok": true }
  }
}
```

### `GET /metrics`

Prometheus text-format metrics. Returns `404` if `ENABLE_METRICS=false`. See
[INFRASTRUCTURE.md](./INFRASTRUCTURE.md) for the full metric list.

---

## Auth — `/api/v1/auth`

### `POST /api/v1/auth/register`

Create an account. No authentication required.

**Request** (`UserCreate`):
```json
{ "email": "candidate@example.com", "password": "a-strong-password", "full_name": "Ada Lovelace" }
```
`password`: 8–128 characters. `full_name`: 1–255 characters.

**Response 201** (`UserResponse`):
```json
{ "id": "9f8c...", "email": "candidate@example.com", "full_name": "Ada Lovelace", "created_at": "2026-06-27T10:00:00Z" }
```

**Errors**: `422` validation error (weak password, malformed email, duplicate email).

### `POST /api/v1/auth/login`

Exchange credentials for tokens. Body is `application/x-www-form-urlencoded`
(OAuth2 password flow: `username` = email, `password`). Rate-limited per
client IP (`RATE_LIMIT_LOGIN_ATTEMPTS` per `RATE_LIMIT_LOGIN_WINDOW_SECONDS`).

**Response 200** (`Token`):
```json
{ "access_token": "eyJ...", "refresh_token": "8f3a...", "token_type": "bearer" }
```

**Errors**: `401` wrong email/password (generic — does not reveal which is
wrong); `423` account locked (progressive backoff after repeated failures —
see [SECURITY.md](../SECURITY.md)); `429` rate-limited.

### `POST /api/v1/auth/refresh`

Rotate a refresh token for a new access/refresh pair. The submitted token is
revoked as part of this call — each refresh token is single-use.

**Request** (`RefreshRequest`): `{ "refresh_token": "8f3a..." }`

**Response 200** (`Token`): same shape as login.

**Errors**: `401` invalid, expired, or already-revoked token. Replaying an
already-revoked token revokes every other active refresh token for that
user (defensive response to suspected token theft).

### `POST /api/v1/auth/logout`

Revoke one refresh token. Does not invalidate the caller's current access
token (it remains valid until natural expiry).

**Request**: `{ "refresh_token": "8f3a..." }` → **Response 200**: `{ "detail": "Logged out" }`

### `GET /api/v1/auth/me` 🔒

Returns the authenticated user (`UserResponse`, same shape as register).

---

## Interview Sessions — `/api/v1/interviews`

All endpoints in this section require auth.

### `POST /api/v1/interviews/`

Create a session (starts in `draft` status).

**Request** (`SessionCreate`):
```json
{ "title": "Backend Engineer @ Acme", "job_role": "Backend Engineer", "job_description": "We are looking for a backend engineer with 3+ years of Python experience..." }
```
`job_description`: 20–10,000 characters (bounded to cap AI token usage).

**Response 201** (`SessionDetailResponse`):
```json
{
  "id": "1a2b...", "title": "Backend Engineer @ Acme", "job_role": "Backend Engineer",
  "job_description": "...", "status": "draft",
  "created_at": "2026-06-27T10:00:00Z", "updated_at": "2026-06-27T10:00:00Z",
  "questions": [], "response_count": 0
}
```

### `GET /api/v1/interviews/`

List the caller's sessions. Query params: `skip` (default `0`), `limit`
(default `50`, max `100`). Returns `list[SessionListResponse]` (a lighter
shape without `job_description`/`questions`).

### `GET /api/v1/interviews/{session_id}`

Full session detail (`SessionDetailResponse`, includes `questions`). `404`
if not found or not owned by the caller.

### `PATCH /api/v1/interviews/{session_id}`

Partially update a **draft** session only.

**Request** (`SessionUpdate`, all fields optional): `{ "title": "New title" }`

**Errors**: `404` not found; `409` session is no longer in `draft` status.

### `DELETE /api/v1/interviews/{session_id}`

Delete a session and everything that cascades from it (questions, audio
responses, transcripts, analyses, report, readiness score, coaching plan —
see [DATABASE.md](./DATABASE.md#cascade-behavior)). **Response 204**.

### `POST /api/v1/interviews/{session_id}/questions/generate`

Generate `MAX_QUESTIONS_PER_SESSION` (default 10) interview questions via
Gemini, categorized (`behavioral`/`technical`/`situational`) and ordered.
Regenerating replaces existing questions.

**Response 201**: `list[QuestionResponse]`
```json
[{ "id": "...", "body": "Tell me about a time you debugged a production incident.", "sequence_order": 1, "category": "behavioral", "source": "ai_generated", "created_at": "..." }]
```

**Errors**: `404` session not found; `409` session not in `draft`; `502`/`503`
Gemini unavailable or timed out.

### `GET /api/v1/interviews/{session_id}/questions`

`list[QuestionResponse]` for the session.

---

## Audio Responses — `/api/v1`

### `POST /api/v1/interviews/{session_id}/responses` 🔒

Upload an audio recording answering one question. `multipart/form-data`:
`file` (binary, `audio/mpeg|wav|webm|ogg|mp4` or `video/mp4`), `question_id`
(form field, UUID).

**Response 201** (`AudioResponseResponse`):
```json
{ "id": "...", "question_id": "...", "status": "uploaded", "created_at": "..." }
```

**Errors**: `404` session/question not found; `413` file exceeds
`MAX_UPLOAD_SIZE_MB`; `415` MIME type not allow-listed; `422` magic-byte
check failed (declared type doesn't match actual file content — see
[SECURITY.md](../SECURITY.md)).

### `GET /api/v1/interviews/{session_id}/responses` 🔒

`list[AudioResponseResponse]` for the session.

### `GET /api/v1/responses/{response_id}/status` 🔒

```json
{ "id": "...", "status": "failed", "created_at": "...", "error_message": null }
```
`error_message` is always a generic, non-leaking string — see
[TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

### `GET /api/v1/responses/{response_id}/transcript` 🔒

```json
{ "id": "...", "audio_response_id": "...", "text": "So in my last role I...", "language": "en", "duration_seconds": 47, "word_count": 132, "created_at": "..." }
```
`404` if the response hasn't reached `completed` yet, or doesn't exist.

### `GET /api/v1/responses/{response_id}/analysis` 🔒

```json
{
  "id": "...", "audio_response_id": "...", "transcript_id": "...",
  "overall_score": "7.5", "communication_score": "8.0", "technical_score": "7.0",
  "problem_solving_score": "7.5", "confidence_score": "7.0",
  "strengths": "[\"Clear structure\", \"Concrete example\"]",
  "weaknesses": "[\"Could quantify impact\"]",
  "detailed_feedback": "...", "model_used": "gemini-2.0-flash", "created_at": "..."
}
```
Scores are serialized as decimal **strings** (0.0–10.0). `strengths` /
`weaknesses` are JSON-encoded arrays inside a string field — parse them
client-side.

### `GET /api/v1/responses/{response_id}/voice-analysis` 🔒

```json
{ "id": "...", "audio_response_id": "...", "speaking_rate": 142.5, "average_pause_duration": 0.8, "total_pause_time": 4.2, "long_pause_count": 2, "filler_word_count": 5, "energy_consistency": 0.82, "confidence_score": 76, "created_at": "..." }
```
`404` if voice analysis wasn't produced (best-effort step — see
[AI_PIPELINE.md](./AI_PIPELINE.md)).

---

## Processing — `/api/v1`

### `POST /api/v1/responses/{response_id}/process` 🔒

Manually (re-)trigger the Whisper → Gemini pipeline for one response.
Idempotent against an already-completed response (no-ops rather than
re-processing).

**Response 202** (`ProcessingStatusResponse`):
```json
{ "response_id": "...", "status": "processing", "transcript_id": null, "analysis_id": null, "error_message": null }
```
**Errors**: `404` not found; `503` `ENABLE_AUDIO_PROCESSING=false`.

### `GET /api/v1/responses/{response_id}/processing-status` 🔒

Same shape as above. This is the endpoint the frontend polls every 3 seconds
(`useProcessingStatus`) until `status` is `completed` or `failed`.

---

## Follow-Up Questions — `/api/v1/interviews` 🔒

### `POST /api/v1/interviews/{session_id}/follow-up-question`

Generates a Gemini follow-up question that probes deeper into one already-
transcribed response.

**Request** (`FollowUpRequest`): `{ "question_id": "...", "response_id": "..." }`

**Response 201** (`FollowUpQuestionResponse`):
```json
{ "id": "...", "session_id": "...", "original_question_id": "...", "parent_audio_response_id": "...", "body": "You mentioned scaling the service — what specifically broke at higher load?", "depth": 1, "created_at": "..." }
```
**Errors**: `404` session/question/response not found; `409` response has no
transcript yet.

### `GET /api/v1/interviews/{session_id}/conversation-history`

Every question for the session paired with its follow-ups
(`list[ConversationTurnResponse]`).

---

## Session Reports — `/api/v1/interviews` 🔒

### `POST /api/v1/interviews/{session_id}/report/generate`

Generates (or regenerates) a holistic Gemini report aggregating every
analyzed response in the session.

**Response 201** (`SessionReportResponse`):
```json
{
  "id": "...", "session_id": "...", "overall_performance": "Strong technical depth with room to improve...",
  "final_score": 7.6, "confidence_score": 74, "communication_score": 7.8, "technical_score": 7.4, "problem_solving_score": 7.5,
  "strengths": "[\"...\"]", "weaknesses": "[\"...\"]",
  "improvement_plan": "...", "readiness_level": "Interview Ready", "model_used": "gemini-2.0-flash", "created_at": "..."
}
```
`readiness_level` ∈ `Beginner | Developing | Interview Ready | Strong
Candidate | Highly Competitive`.

### `GET /api/v1/interviews/{session_id}/report`

Same shape. `404` if no report has been generated yet.

---

## Live Conversational Interviews — `/api/v1/live-interviews` 🔒

### `POST /api/v1/live-interviews/`

Start a multi-turn AI interview and receive the first question.

**Request** (`StartLiveInterviewRequest`):
```json
{ "job_role": "Backend Engineer", "job_description": "...", "max_turns": 5 }
```
`max_turns`: 3–10, default 5.

**Response 201** (`LiveInterviewSessionResponse`):
```json
{
  "id": "...", "user_id": "...", "job_role": "Backend Engineer", "job_description": "...",
  "status": "active", "current_turn": 1, "max_turns": 5,
  "created_at": "...", "completed_at": null,
  "turns": [{ "id": "...", "live_session_id": "...", "turn_number": 1, "question_text": "Tell me about yourself.", "difficulty_level": 1, "response_text": null, "audio_response_id": null, "created_at": "..." }],
  "current_question": { "...": "same shape as above" }
}
```

### `POST /api/v1/live-interviews/{session_id}/next-question`

Submit the candidate's answer to the current turn and receive the next
question (difficulty scales 1→5 across turns).

**Request** (`NextQuestionRequest`): `{ "response_text": "I've been a backend engineer for...", "audio_response_id": null }`

**Errors**: `404` not found; `409` session already `completed` or
`max_turns` reached.

### `GET /api/v1/live-interviews/{session_id}/conversation`

Full `LiveInterviewSessionResponse` including all turns so far.

### `POST /api/v1/live-interviews/{session_id}/end`

End the session early and generate a closing summary.

**Response 200** (`EndInterviewResponse`):
```json
{ "session_id": "...", "status": "completed", "total_turns": 4, "summary": "...", "turns": [/* ConversationTurnResponse[] */] }
```

---

## Resume / RAG — `/api/v1/documents` 🔒

### `POST /api/v1/documents/resume/upload`

`multipart/form-data`: `file` (PDF or DOCX). Text is extracted
(`pypdf`/`python-docx`), chunked into 200-word overlapping windows
(`RAG_CHUNK_SIZE`/`RAG_CHUNK_OVERLAP`), and embedded
(`sentence-transformers`). Replaces any previously uploaded resume.

**Response 201** (`ResumeDocumentResponse`):
```json
{ "id": "...", "user_id": "...", "filename": "resume.pdf", "extracted_text": "Ada Lovelace\nBackend Engineer...", "created_at": "...", "chunk_count": 14 }
```
**Errors**: `413` too large (`MAX_RESUME_UPLOAD_SIZE_MB`); `415` not
PDF/DOCX; `422` magic-byte mismatch, malware-scan rejection, or text
extraction failure (e.g. an image-only/scanned PDF with no extractable text).

### `GET /api/v1/documents/resume/current`

The most recently uploaded resume. `404` if none uploaded yet.

### `POST /api/v1/documents/interviews/{session_id}/generate-rag-questions`

Generate questions personalized to the candidate's resume via top-k cosine
similarity retrieval over their `document_chunks`.

**Request** (`RAGQuestionsRequest`): `{ "count": 5 }` (1–20, default 5)

**Response 201** (`RAGQuestionsResponse`):
```json
{ "session_id": "...", "questions": [{ "body": "Your resume mentions migrating a monolith to microservices — walk me through that decision.", "category": "technical", "sequence_order": 1 }], "resume_context_used": true, "chunks_retrieved": 5 }
```
`resume_context_used: false` if the candidate has no resume uploaded —
questions fall back to job-description-only generation rather than failing.

---

## Interview Readiness Score & Career Coaching — `/api/v1` 🔒

### `POST /api/v1/interviews/{session_id}/readiness`

Computes a transparent, deterministic weighted average over the session's
analyzed responses (see [AI_PIPELINE.md §9](./AI_PIPELINE.md#9-interview-readiness-scoring--benchmarking-prediction_servicepy-benchmark_servicepy)
for the exact weights). **Not** a machine-learned prediction of a
real-world interview or hiring outcome.

**Response 201** (`InterviewReadinessResponse`):
```json
{ "id": "...", "session_id": "...", "readiness_score": 0.78, "percentile_rank": 82.5, "readiness_level": "Strong", "scoring_method": "weighted-v1", "created_at": "..." }
```
`readiness_level` ∈ `Excellent | Strong | Developing | Needs Improvement`.

**Errors**: `422` no analyzed responses in the session yet.

### `GET /api/v1/interviews/{session_id}/readiness`

Same shape. `404` if not yet generated.

### `POST /api/v1/interviews/{session_id}/coaching-plan`

**Response 201** (`CoachingPlanResponse`):
```json
{ "id": "...", "session_id": "...", "plan_7_day": ["Day 1: ...", "Day 2: ..."], "plan_14_day": [/* ... */], "plan_30_day": [/* ... */], "focus_areas": ["System design depth", "Quantifying impact"], "model_used": "gemini-2.0-flash", "created_at": "..." }
```

### `GET /api/v1/interviews/{session_id}/coaching-plan`

Same shape. `404` if not yet generated.

### `GET /api/v1/analytics/benchmarks`

```json
{ "user_average_score": 7.4, "percentile_rank": 71.0, "total_platform_responses": 1842, "user_responses_analyzed": 12 }
```
Computed via SQL aggregates (`COUNT`/`AVG`), not loaded into Python row by
row — see [AI_PIPELINE.md](./AI_PIPELINE.md#benchmarking).

---

## Analytics — `/api/v1/analytics` 🔒

### `GET /api/v1/analytics/overview`

```json
{ "total_sessions": 9, "completed_sessions": 6, "average_overall_score": 7.3, "total_responses_analyzed": 41, "strongest_skill": "communication", "weakest_skill": "technical", "improvement_score": 0.6 }
```
All fields are `null`/`0` if the user has no data yet, rather than erroring.

### `GET /api/v1/analytics/trends`

`list[SessionTrendResponse]`, one entry per session, each with the four
per-category average scores — what powers the dashboard's `LineChart`.

---

## Error response shape

Every non-2xx response (except FastAPI's own `422` validation responses)
shares one shape:

```json
{ "detail": "A short, generic, user-safe message" }
```

Raw exception text, stack traces, and AI-provider error bodies are never
forwarded to the client — see `app/core/exceptions.py` and
[SECURITY.md](../SECURITY.md). `422` validation errors use FastAPI/Pydantic's
standard `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` shape.

## Related documentation

- [DATABASE.md](./DATABASE.md) — the schema backing every response model.
- [AI_PIPELINE.md](./AI_PIPELINE.md) — what happens between an upload and a
  finished transcript/analysis.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — the authentication flow diagram.
