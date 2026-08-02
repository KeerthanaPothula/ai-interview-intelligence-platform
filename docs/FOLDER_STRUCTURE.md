# Folder Structure

A file-by-file map of both codebases. For the condensed version see the
root [README § Folder structure](../README.md#folder-structure); this doc
goes one level deeper into `app/` and `src/`.

## Backend — `backend/app/`

```
backend/app/
├── main.py                 # FastAPI app construction, middleware wiring,
│                            # /health, /ready, /metrics
├── config.py                # pydantic-settings — every env var, typed and validated
├── database.py               # SQLAlchemy engine/session factory
│
├── models/                   # SQLAlchemy ORM models — one file per domain
│   ├── user.py                  # User, refresh-token relationship
│   ├── refresh_token.py         # Hashed, rotating refresh tokens
│   ├── password_reset_token.py
│   ├── interview.py             # InterviewSession, Question
│   ├── analysis.py              # AudioResponse, Transcript, InterviewAnalysis
│   ├── documents.py             # ResumeDocument, DocumentChunk (RAG)
│   ├── conversation.py          # Live conversational interview turns
│   ├── features.py              # SessionReport, VoiceAnalysis, FollowUpQuestion
│   └── prediction.py            # InterviewPrediction, CoachingPlan
│
├── schemas/                  # Pydantic request/response models — mirrors models/
│   └── ... (one file per domain, plus admin.py, recruiter.py)
│
├── routers/                  # FastAPI routers — one file per resource
│   ├── auth.py                   # register/login/refresh/me/password reset
│   ├── interviews.py             # session CRUD + question generation
│   ├── responses.py              # audio upload + transcript/analysis retrieval
│   ├── processing.py             # manual reprocessing trigger + status polling
│   ├── follow_up.py              # AI follow-up questions
│   ├── reports.py                # session report generation
│   ├── live_interview.py         # conversational interview turns
│   ├── documents.py              # resume upload, RAG question generation
│   ├── prediction.py             # readiness score, coaching plan, benchmarks
│   ├── analytics.py              # per-user dashboard/analytics endpoints
│   ├── recruiter.py              # candidate aggregation (added this pass)
│   └── admin.py                  # platform-wide dashboard (added this pass)
│
├── services/                 # Business logic — routers stay thin, call into here
│   ├── auth_service.py             # password hashing, lockout, token issuance
│   ├── gemini_service.py           # low-level Gemini client wrapper
│   ├── question_service.py         # question generation orchestration
│   ├── transcription_service.py    # Whisper wrapper
│   ├── evaluation_service.py       # Gemini answer evaluation
│   ├── voice_analysis_service.py   # librosa acoustic analysis
│   ├── processing_service.py       # the upload→transcript→analysis pipeline + startup recovery
│   ├── follow_up_service.py
│   ├── report_service.py
│   ├── interview_conversation_service.py  # live interview turn logic
│   ├── document_extraction_service.py     # PDF/DOCX text extraction
│   ├── embedding_service.py               # sentence-transformers wrapper
│   ├── rag_service.py                     # chunk retrieval + resume-grounded prompting
│   ├── prediction_service.py              # readiness score formula
│   ├── benchmark_service.py               # percentile ranking
│   ├── career_coach_service.py            # 7/14/30-day coaching plans
│   ├── recruiter_service.py               # candidate aggregation (added this pass)
│   ├── resume_scoring.py                  # shared ATS-score heuristic (added this pass)
│   ├── admin_service.py                   # platform stats aggregation (added this pass)
│   └── upload_service.py                  # file validation + disk I/O
│
└── core/                     # Cross-cutting concerns, no domain logic
    ├── security.py               # JWT signing/verification
    ├── deps.py                   # get_current_user, get_db FastAPI dependencies
    ├── pagination.py              # shared skip/limit dependency
    ├── rate_limit.py              # in-memory per-IP login rate limiting
    ├── file_validation.py         # MIME allow-list, magic bytes, size ceiling
    ├── security_headers.py        # CSP, HSTS, X-Frame-Options middleware
    ├── security_logging.py        # structured security-event logger
    ├── exceptions.py              # AppException hierarchy + global handlers
    ├── ai_reliability.py          # retry/backoff/JSON-repair for every Gemini call
    ├── middleware.py              # request-ID correlation, slow-request logging
    ├── logging_config.py          # structured JSON logging setup
    ├── metrics.py                 # Prometheus counters/histograms
    ├── tracing.py                 # optional OpenTelemetry setup
    ├── request_context.py         # contextvars for request-scoped state
    └── constants.py               # API_V1_PREFIX and other shared constants
```

`tests/` mirrors this structure loosely — one `test_*.py` per router/feature
(267 tests total; see [TESTING.md](./TESTING.md)). `alembic/` holds the
migration history (see [DATABASE.md § Migration history](./DATABASE.md)).

## Frontend — `frontend/src/`

```
frontend/src/
├── main.tsx                # React root render
├── App.tsx                  # Route table, lazy-loaded page imports
├── index.css                 # The entire design-token system + every
│                              # component's styles (no CSS-in-JS, no modules)
│
├── api/
│   ├── client.ts                # Every backend call — one typed function per endpoint
│   └── types.ts                  # Request/response TypeScript interfaces, mirrors backend schemas/
│
├── context/                  # React context providers, one per cross-cutting concern
│   ├── AuthContext.tsx            # token state, login/register/logout
│   ├── ThemeContext.tsx           # dark/light theme, persisted (added this pass)
│   ├── ToastContext.tsx           # global toast notifications
│   └── FeaturesContext.tsx        # feature-flag-style toggles
│
├── hooks/
│   └── useProcessingStatus.ts    # polls processing-status until terminal
│
├── components/                # Shared UI, used across multiple pages
│   ├── Layout.tsx                 # authenticated shell: sidebar + topbar + <Outlet>
│   ├── Sidebar.tsx / TopBar.tsx    # primary navigation
│   ├── ThemeToggle.tsx             # Sun/Moon toggle button (added this pass)
│   ├── NotificationBell.tsx
│   ├── ScreenshotsCarousel.tsx     # landing-page screenshot carousel (added this pass)
│   ├── Skeleton.tsx                 # loading-state placeholders
│   ├── StateMessage.tsx             # EmptyState / ErrorState
│   ├── SessionCard.tsx / SessionReportCard.tsx
│   ├── QuestionCard.tsx / ResponseCard.tsx
│   ├── TranscriptCard.tsx / AnalysisCard.tsx / VoiceAnalyticsCard.tsx
│   ├── ProcessingStatusCard.tsx
│   ├── ResumeUploadCard.tsx
│   └── OfflineBanner.tsx
│
└── pages/                     # One component per route
    ├── LandingPage.tsx             # public marketing page (`/`)
    ├── LoginPage.tsx / RegisterPage.tsx / ForgotPasswordPage.tsx / ResetPasswordPage.tsx
    ├── DashboardPage.tsx            # `/dashboard`
    ├── SessionsListPage.tsx         # `/sessions`
    ├── SessionDetailPage.tsx        # `/sessions/:sessionId`
    ├── InterviewReportPage.tsx      # `/sessions/:sessionId/report` — includes PDF export
    ├── LiveInterviewPage.tsx        # `/live-interview`
    ├── AnalyticsPage.tsx            # `/analytics`
    ├── ResumePage.tsx               # `/resume`
    ├── ProfilePage.tsx              # `/profile`
    ├── RecruiterPage.tsx            # `/recruiter` — live backend data
    ├── AdminPage.tsx                # `/admin` — live backend data (added this pass)
    └── NotFoundPage.tsx
```

Route-based code splitting (`React.lazy`) applies to every page under
`Layout` — each compiles to its own chunk (`dist/assets/AdminPage-*.js`,
etc.), confirmed in the production build output. `LandingPage` and the
four auth pages load eagerly since they're tiny and are what an
unauthenticated visitor sees first.
