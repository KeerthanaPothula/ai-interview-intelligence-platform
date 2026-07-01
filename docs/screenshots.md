# Screenshots

Screenshots live in `docs/screenshots/`. Four were captured automatically
via Playwright against a real running stack (no mocking); five require a
session with completed Whisper transcription + Gemini analysis to capture.

## Captured (real, from a running local stack)

| # | File | Page |
|---|---|---|
| 1 | [`docs/screenshots/01-login.png`](screenshots/01-login.png) | Login page (`/login`) |
| 2 | [`docs/screenshots/02-register.png`](screenshots/02-register.png) | Registration form (`/register`) |
| 3 | [`docs/screenshots/03-session-list.png`](screenshots/03-session-list.png) | Sessions list with resume upload card and create-session form (`/`) |
| 4 | [`docs/screenshots/04-session-detail.png`](screenshots/04-session-detail.png) | Session detail before questions are generated (`/sessions/:id`) |

## Still needed (require a Gemini API key and a completed session)

To capture these, run the full app with a real `GEMINI_API_KEY`, complete
at least one interview session (upload audio → wait for Whisper + Gemini
to finish), then screenshot each state.

| # | Filename | Page / Component | How to capture |
|---|---|---|---|
| 5 | `docs/screenshots/05-questions.png` | `SessionDetailPage` — question list | After clicking "Generate Questions" — shows the Gemini-generated question list (category + text). |
| 6 | `docs/screenshots/06-upload.png` | `SessionDetailPage` — `QuestionCard` upload control | A question card with the file picker ready to upload. |
| 7 | `docs/screenshots/07-processing.png` | `ResponseCard` → `ProcessingStatusCard` | Immediately after upload, while `status === 'processing'` (spinner visible). |
| 8 | `docs/screenshots/08-transcript.png` | `ResponseCard` → `TranscriptCard` | After processing — transcript text, language, word count, duration. |
| 9 | `docs/screenshots/09-analysis.png` | `ResponseCard` → `AnalysisCard` | Same completed response — all 5 scores, strengths/weaknesses lists, detailed feedback. |
| 10 | `docs/screenshots/10-report.png` | `SessionDetailPage` → `SessionReportCard` | After clicking "Generate Report" — readiness score, level, performance summary. |
| 11 | `docs/screenshots/11-dashboard.png` | `DashboardPage` (`/dashboard`) | Analytics overview with session count, trend chart, and benchmarking. |

## Capture setup

```bash
# Resize browser to 1440×900 for consistency
# Use realistic but non-sensitive sample data

# Start the stack
cd backend && uvicorn app.main:app --port 8000 --reload
cd frontend && npm run dev

# Open http://localhost:5173 in a browser
# Navigate to each page listed above and screenshot manually
# Save to docs/screenshots/ using the exact filenames
```

Once all files are in place, the table in
[README.md § Screenshots](../README.md#screenshots) can be replaced with
inline image embeds.
