# Architecture

This document expands on the high-level diagram in [README.md](../README.md)
with two views of the system:

1. **Request architecture** — how the frontend, backend, and database fit
   together.
2. **Audio processing pipeline** — what happens to an uploaded recording from
   the moment it's submitted to the moment its transcript and AI analysis are
   available.

---

## 1. Request Architecture

```mermaid
flowchart TB
    subgraph Client["Browser"]
        SPA["React SPA\n(Vite + TypeScript)"]
    end

    subgraph Backend["FastAPI Backend (Docker)"]
        MW["CORS + JWT Auth\nMiddleware/Dependency"]
        Routers["Routers\nauth · interviews · questions\nresponses · processing"]
        Services["Services\nauth · interview · question\nupload · transcription · evaluation"]
        ORM["SQLAlchemy ORM"]
    end

    DB[("PostgreSQL")]
    FS[("Uploads Volume\n/app/uploads")]
    Gemini["Google Gemini API"]
    Whisper["Whisper Model\n(in-process, CPU)"]

    SPA -- "HTTPS + JWT Bearer" --> MW
    MW --> Routers
    Routers --> Services
    Services --> ORM
    ORM --> DB
    Services -- "store/read audio files" --> FS
    Services -- "generate questions\nevaluate transcript" --> Gemini
    Services -- "transcribe audio" --> Whisper
```

**Key points**

- The SPA never talks to PostgreSQL, Gemini, or Whisper directly — every
  external interaction is mediated by the FastAPI backend.
- `CORS_ORIGINS` and the JWT dependency gate every route except `/health`,
  `/api/v1/auth/register`, and `/api/v1/auth/login`.
- Whisper runs **in-process** as a module-level singleton (one model load per
  backend instance, guarded by a semaphore) — there is no separate ML service.
- Uploaded audio is written to a volume (`docker-compose` bind mount locally,
  a Render Disk in production) so files survive container restarts.

---

## 2. Audio Processing Pipeline

From upload to a finished transcript + AI evaluation:

```mermaid
flowchart LR
    A["Candidate uploads audio\nPOST /interviews/{id}/responses"] --> B["AudioResponse created\nstatus = uploaded"]
    B --> C["POST /responses/{id}/process\n(background task started)"]
    C --> D["status = processing"]
    D --> E["Whisper transcription\n(bounded by WHISPER_TIMEOUT_SECONDS)"]
    E -->|success| F["Transcript saved\n(text, language, word_count, duration)"]
    E -->|failure / timeout| Z1["status = failed\n(generic error_message)"]
    F --> G["Gemini evaluation\n(transcript truncated to\nMAX_TRANSCRIPT_CHARS)"]
    G -->|success| H["InterviewAnalysis saved\n(5 scores + strengths/\nweaknesses + feedback)"]
    G -->|failure| Z1
    H --> I["status = completed"]

    style Z1 fill:#f8d7da,stroke:#c00
    style I fill:#d4edda,stroke:#0a0
```

**Status lifecycle** (`AudioResponse.status`):

```mermaid
stateDiagram-v2
    [*] --> uploaded
    uploaded --> processing : POST /responses/{id}/process
    processing --> completed : transcription + evaluation succeed
    processing --> failed : Whisper or Gemini error/timeout
    failed --> processing : retry (re-upload / re-process)

    note right of processing
        On backend startup, any response
        stuck in "processing" (e.g. from a
        crash) is recovered back to "failed".
    end note
```

**Frontend polling**

The `ResponseCard` component uses `useProcessingStatus`, which polls
`GET /responses/{id}/processing-status` every 3 seconds while
`status` is `uploaded` or `processing`. Polling stops automatically once the
status becomes `completed` or `failed`. On `completed`, the frontend fetches
`GET /responses/{id}/transcript` and `GET /responses/{id}/analysis` and
renders `TranscriptCard` / `AnalysisCard`. On `failed`, only a generic
retry message is shown — the raw `error_message` is never displayed.

---

## Related Documentation

- [DEPLOYMENT.md](./DEPLOYMENT.md) — migration strategy and persistent
  storage rationale.
- [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) — step-by-step Render setup
  that realizes the request architecture above in production.
