# Portfolio Assets

Ready-to-use copy for resumes, LinkedIn, and a personal portfolio site.
Adjust names, links, and metrics (e.g. test counts) if the project evolves.

---

## Resume Bullet Points

Pick 2–4 depending on space. Written for a "Projects" or "Personal Projects"
resume section.

- Designed and built a full-stack **AI Interview Intelligence Platform**
  (FastAPI, React, TypeScript, PostgreSQL) that generates role-specific
  interview questions and evaluates candidates' spoken answers using
  **Google Gemini** and **OpenAI Whisper**.
- Implemented a JWT-based authentication system with strict per-user data
  isolation (ownership checks on every resource, 404-not-403 to prevent
  enumeration) and an environment-driven CORS policy.
- Built an asynchronous audio-processing pipeline (upload → Whisper
  transcription → Gemini evaluation) with status tracking, timeouts, and
  crash recovery, exposed to the frontend via a polling status API.
- Containerized the backend with Docker and authored a production deployment
  guide for Render (managed PostgreSQL, persistent disk for uploads, Alembic
  migrations via pre-deploy hook, static-site frontend with SPA routing).
- Wrote a 108-test suite (94 backend pytest tests, 14 frontend Vitest/RTL
  tests) covering auth, ownership, the processing pipeline, and key UI
  components.

---

## LinkedIn Project Description

Use in the **Projects** section of a LinkedIn profile (supports a title,
description, and optional link).

**Title:** AI Interview Intelligence Platform

**Description:**

> A full-stack web application that helps candidates practice for job
> interviews using AI. Users create a mock interview session for a target
> role, and the platform (via Google Gemini) generates tailored interview
> questions. Candidates upload audio recordings of their answers, which are
> automatically transcribed with OpenAI Whisper and evaluated by Gemini
> across five dimensions — communication, technical depth, problem solving,
> confidence, and overall performance — with detailed written feedback.
>
> Built with FastAPI, SQLAlchemy, and PostgreSQL on the backend and React +
> TypeScript on the frontend, with JWT authentication, per-user data
> isolation, an asynchronous processing pipeline with live status polling,
> and a Dockerized deployment to Render. Includes a 108-test automated suite
> across backend (pytest) and frontend (Vitest + React Testing Library).

---

## Portfolio Website Description

### Short version (project card / grid)

> **AI Interview Intelligence Platform** — A full-stack app that generates
> AI interview questions, transcribes spoken answers with Whisper, and scores
> them with Gemini across five dimensions. FastAPI · React · TypeScript ·
> PostgreSQL · Docker.

### Long version (project detail page)

> ## AI Interview Intelligence Platform
>
> A production-shaped, full-stack platform for AI-assisted mock interview
> practice.
>
> **The problem:** practicing for interviews is hard without structured
> feedback — candidates often don't know how their answers actually sound or
> where they fall short.
>
> **The solution:** candidates create an interview session for a target job
> role and get back AI-generated, role-specific questions (via Google
> Gemini). After recording an answer and uploading it, the platform
> transcribes the audio locally with OpenAI Whisper and sends the transcript
> to Gemini for evaluation — returning scores for communication, technical
> depth, problem solving, confidence, and overall performance, plus written
> strengths, weaknesses, and detailed feedback.
>
> **Highlights:**
> - JWT authentication with strict per-user ownership on every resource
> - Asynchronous processing pipeline (Whisper → Gemini) with status tracking,
>   timeouts, and crash recovery, surfaced to the UI via polling
> - Environment-driven CORS policy and hardened production configuration
> - Dockerized backend with a documented Render deployment (managed
>   PostgreSQL, persistent disk for uploads, Alembic migrations)
> - 108 automated tests across backend (pytest) and frontend (Vitest + React
>   Testing Library)
>
> **Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React, TypeScript,
> Vite, Docker, Render.
>
> [GitHub repository](#) · [Live demo](#)
