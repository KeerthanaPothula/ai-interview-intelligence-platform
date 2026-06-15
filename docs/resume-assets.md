# Resume Assets

Multiple framings of the same project for different contexts. Pick the
version that fits the format you're filling out — don't mix bullet styles
within a single resume.

---

## Version A — ATS-Friendly Resume Bullets

Plain language, explicit technology names, no special characters that ATS
parsers mangle. Use for resumes submitted through applicant tracking systems.

- Developed a full-stack web application using FastAPI, React, TypeScript,
  and PostgreSQL that generates AI interview questions and evaluates
  candidate responses.
- Implemented JWT-based user authentication and authorization with
  per-user data access control across all API endpoints.
- Integrated Google Gemini API for AI-generated interview questions and
  automated response evaluation across five scoring categories.
- Integrated OpenAI Whisper for server-side audio transcription, including
  language detection, word count, and duration metrics.
- Built an asynchronous background processing pipeline with status
  tracking, timeout handling, and automatic recovery from failed jobs.
- Designed a relational database schema with 6 tables, foreign key
  cascades, and Alembic migrations for PostgreSQL.
- Wrote 108 automated tests (94 backend with pytest, 14 frontend with
  Vitest and React Testing Library) covering authentication, authorization,
  and the processing pipeline.
- Containerized the backend with Docker and documented a production
  deployment to Render, including managed PostgreSQL, persistent storage,
  and database migrations.

---

## Version B — Impact-Focused Resume Bullets

Emphasizes outcomes, design decisions, and the "why." Use for resumes
reviewed by engineers/hiring managers, or as talking points to expand on
verbally.

- Architected an end-to-end AI interview-practice platform — from JWT auth
  and a PostgreSQL schema with cascading ownership rules, to an
  AI-evaluation pipeline combining **Whisper** (transcription) and
  **Gemini** (scoring) — taking it from design through a documented
  production deployment.
- Closed a real security gap by enforcing per-user ownership on every
  resource and returning identical 404s for "not found" and "not yours,"
  preventing resource enumeration across users.
- Designed an asynchronous processing pipeline (upload → transcribe →
  evaluate) with explicit status states, timeouts, and startup recovery for
  jobs interrupted by a crash — so a single failure mode never leaves a
  user's request stuck.
- Made deliberate cost/precision trade-offs in the data model — e.g. using
  `NUMERIC(4,1)` with `Decimal` conversion for AI scores to avoid float
  rounding errors, and string-based status columns instead of DB enums to
  avoid migration lock contention.
- Built confidence in correctness with a 108-test suite spanning
  authorization edge cases, state-machine transitions, and UI states
  (including failure and loading states) — not just happy paths.
- Took the project from local development to a documented, reproducible
  Render deployment (Docker web service, managed PostgreSQL, persistent
  disk, pre-deploy migrations, static frontend with SPA routing).

---

## Version C — Short Project Description (1 line)

> AI Interview Intelligence Platform — a full-stack FastAPI/React app that
> generates AI interview questions, transcribes audio answers with Whisper,
> and scores them with Gemini.

---

## Version D — Medium Project Description (3–4 lines)

> AI Interview Intelligence Platform is a full-stack application for mock
> interview practice. Users get AI-generated, role-specific interview
> questions (via Google Gemini), record audio answers, and receive an
> automatic transcript (via OpenAI Whisper) plus a five-dimension AI
> evaluation with written feedback. Built with FastAPI, SQLAlchemy,
> PostgreSQL, and React/TypeScript, with JWT auth, an asynchronous
> processing pipeline, a 108-test suite, and a documented Docker/Render
> deployment.

---

## Version E — Interview Explanation

**Question: "Tell me about this project."**

> Sure — I built an AI Interview Intelligence Platform, which is basically a
> tool for practicing job interviews and getting structured feedback.
>
> The flow is: a user creates an interview session by entering a target job
> role and description. The backend calls Google's Gemini API to generate a
> set of role-specific interview questions. The user then records or uploads
> an audio answer for each question. That kicks off a background processing
> pipeline — first OpenAI Whisper transcribes the audio locally on the
> server, and then the transcript gets sent to Gemini again, this time to be
> scored across five dimensions: communication, technical depth, problem
> solving, confidence, and an overall score, along with written strengths,
> weaknesses, and detailed feedback.
>
> On the backend, I used FastAPI with SQLAlchemy and PostgreSQL, with
> Alembic for migrations. One thing I focused on was the security model —
> every resource is scoped to the owning user, and if you try to access
> someone else's session or response, you get a 404, not a 403 — so you
> can't even tell whether the resource exists. I also designed the audio
> processing as an explicit state machine — `uploaded → processing →
> completed/failed` — with timeouts on both the Whisper and Gemini calls,
> and a startup check that recovers any job stuck in `processing` (say, from
> a crash) back to `failed` so it doesn't sit there forever.
>
> The frontend is React and TypeScript, built with Vite. It polls a
> processing-status endpoint every few seconds while a response is being
> processed, and once it's done, it fetches and renders the transcript and
> the analysis. I made sure raw error messages never reach the UI — failures
> show a generic retry message instead.
>
> I also wrote a fairly large test suite — 94 backend tests with pytest and
> 14 frontend tests with Vitest and React Testing Library — covering auth,
> ownership checks, the processing state machine, and the key UI states
> including failures.
>
> Finally, I containerized the backend with Docker and wrote up a full
> deployment guide for Render — a Docker web service for the API, a managed
> PostgreSQL database, a persistent disk for uploaded audio, and a static
> site for the frontend, including the Alembic migration step and the CORS
> configuration needed to connect them.
>
> If I kept working on it, the next things I'd add are in-browser audio
> recording instead of file upload, moving uploaded audio to object storage
> like S3 for horizontal scaling, and a proper job queue instead of in-process
> background tasks.
