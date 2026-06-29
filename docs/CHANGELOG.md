# Changelog

All notable changes to this project, grouped by date. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project has
not yet tagged any releases, so entries are organized by commit date rather
than version number — see [CONTRIBUTING.md § Versioning](./CONTRIBUTING.md#versioning--releases)
for the semantic-versioning scheme recommended starting with the first
tagged release.

## 2026-06-29

- **fix**: resolved GitHub Actions CI failures (`openai-whisper` build
  failure from an unpinned `pkg_resources` transitive dependency; an
  ineffective `cache: "pip"` step) — all six CI jobs green.
- **feat**: production infrastructure, observability, and CI/CD — GitHub
  Actions (`ci.yml`, `security.yml`), structured JSON logging with
  request-ID correlation, Prometheus metrics (`/metrics`), optional
  OpenTelemetry tracing, `/health` + `/ready` endpoints, hardened
  multi-stage non-root Docker build. See [INFRASTRUCTURE.md](./INFRASTRUCTURE.md).

## 2026-06-28

- **feat**: production security hardening — see [SECURITY.md](./SECURITY.md)
  and the root [SECURITY.md](../SECURITY.md) for the full set of controls
  (account lockout, refresh-token rotation, security headers, file upload
  validation).

## 2026-06-27

- **feat**: backend architecture refactor and reliability improvements —
  atomic response claiming, a process-wide Whisper inference semaphore,
  idempotent processing retries, and startup recovery for responses stuck
  in `processing`. See [AI_PIPELINE.md § 1](./AI_PIPELINE.md#1-audio-response-pipeline-whisper--gemini--librosa).

## 2026-06-18

- **feat**: live conversational AI interviews, resume/JD RAG question
  generation, predictive analytics (success probability + percentile
  benchmarking), and AI career coaching (7/14/30-day plans). See
  [AI_PIPELINE.md §§ 6–10](./AI_PIPELINE.md).
- **feat**: voice analytics engine (librosa), AI follow-up interviewer,
  analytics dashboard, and session-level final reports. See
  [AI_PIPELINE.md §§ 4–5, 8](./AI_PIPELINE.md).

## 2026-06-15

- **docs**: repository presentation pass — career/portfolio assets, Render
  deployment preparation.
- **feat**: integrated transcript and analysis views into the frontend
  (the first version of the polling-based processing UI).

## 2026-06-12

- **feat**: Week 3 audio processing and AI evaluation pipeline — Whisper
  transcription, Gemini evaluation, transcript/analysis retrieval and
  processing-status endpoints, interview-session state-transition
  enforcement.
- **fix**: corrected session-completion criteria.
- **security**: hardened the transcript-evaluation prompt (prompt-injection
  resistance) and the CORS configuration (exact-origin allowlist, no
  wildcard).
- **chore**: production logging configuration; backend deployment
  preparation.

## 2026-06-09

- Week 2 complete — stable baseline ahead of the Whisper pipeline (auth,
  interview sessions, question generation).

## 2026-06-07

- Initial commit; Week 1 backend foundation (FastAPI app skeleton, user
  auth, interview-session CRUD).

## Related documentation

- [CONTRIBUTING.md](./CONTRIBUTING.md) — versioning scheme for future releases.
- [ARCHITECTURE.md](./ARCHITECTURE.md) / [AI_PIPELINE.md](./AI_PIPELINE.md) — what the current architecture looks like after all entries above.
