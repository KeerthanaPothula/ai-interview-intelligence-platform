# GitHub Profile Content

Copy for showcasing this repository on GitHub itself — the repo's "About"
field, a GitHub profile README, and a pinned-repository write-up.

---

## Short GitHub Project Description

For the repository's **About** field (top-right of the repo page, also used
for search/SEO). Keep it under ~160 characters.

> Full-stack AI interview practice platform — FastAPI + React app that
> generates interview questions, transcribes audio with Whisper, and scores
> answers with Gemini.

**Suggested topics/tags:** `fastapi` `react` `typescript` `postgresql`
`docker` `openai-whisper` `google-gemini` `jwt-authentication`
`full-stack` `render`

---

## Featured-Project Text

For a "Featured Projects" or "Things I've Built" section in a GitHub profile
README (`username/username` repo). Designed to sit alongside a thumbnail or
screenshot and a link.

```markdown
### 🎤 AI Interview Intelligence Platform

A full-stack app for AI-assisted mock interview practice. Generates
role-specific interview questions with **Google Gemini**, transcribes
recorded audio answers with **OpenAI Whisper**, and returns a 5-dimension
AI evaluation (communication, technical depth, problem solving, confidence,
overall) with written feedback.

**Stack:** FastAPI · SQLAlchemy · PostgreSQL · React · TypeScript · Docker

- JWT auth with per-user data isolation
- Asynchronous processing pipeline with status polling and crash recovery
- 108 automated tests (pytest + Vitest/RTL)
- Documented Docker + Render deployment

🔗 [Repository](#) · [Architecture docs](docs/architecture.md)
```

---

## Pinned Repository Description

When pinning this repo (GitHub Profile → Customize your pins), GitHub shows
the repo's About description automatically, plus language and star count —
so the **Short GitHub Project Description** above is what will display.

If instead writing a dedicated "Pinned Projects" callout in a profile
README (more space than the About field), use:

```markdown
**[AI Interview Intelligence Platform](#)** — Full-stack platform that
generates AI interview questions (Gemini), transcribes spoken answers
(Whisper), and scores them across 5 dimensions with detailed feedback.
FastAPI/PostgreSQL backend, React/TypeScript frontend, JWT auth,
Dockerized and deployed on Render. 108 automated tests.
```
