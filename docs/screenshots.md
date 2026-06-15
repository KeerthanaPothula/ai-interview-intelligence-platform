# Screenshot Plan

This document is the capture checklist for the screenshots referenced in
[README.md](../README.md#screenshots). None of these images exist yet —
this file specifies exactly what to capture, the filename/path each image
must be saved to, and how to get the app into the right state for each one.

## Setup

1. Run the app locally (`docker-compose up` or the two `npm run dev` /
   `uvicorn` processes — see [README § Local Setup](../README.md#local-setup)).
2. Use a browser window sized to roughly **1440×900** for consistency.
3. Use realistic but non-sensitive sample data (a fictional candidate name,
   a generic job role like "Backend Engineer").
4. Save all files as **PNG**, in `docs/screenshots/`, using the exact
   filenames below — the README table links to these paths directly.

## Checklist

| # | Filename | Page / Component | How to capture |
|---|---|---|---|
| 1 | `docs/screenshots/01-login.png` | `LoginPage` (`/login`) | Logged out, empty or filled login form. Show the app name/branding and the email + password fields. |
| 2 | `docs/screenshots/02-register.png` | `RegisterPage` (`/register`) | Registration form with name/email/password fields visible. |
| 3 | `docs/screenshots/03-session-list.png` | `SessionsListPage` (`/`) | Logged in, with **at least 2–3 sessions** in different statuses (`draft`, `in_progress`, `completed`) so the status badges are visible. Include the "create session" form/button. |
| 4 | `docs/screenshots/04-session-detail.png` | `SessionDetailPage` (`/sessions/:id`) | A session in `in_progress` showing its title, job role/description, and the question list with at least one question that has a response. |
| 5 | `docs/screenshots/05-questions.png` | `SessionDetailPage` — `QuestionCard` list | Right after clicking "Generate Questions" — show the full Gemini-generated question list (category + question text) for a `draft` session. |
| 6 | `docs/screenshots/06-upload.png` | `SessionDetailPage` — `QuestionCard` upload control | A question card with the file picker open/focused, ready to upload an audio recording (`accept="audio/*"`). |
| 7 | `docs/screenshots/07-processing.png` | `ResponseCard` → `ProcessingStatusCard` | Immediately after upload, while `status` is `processing` — capture the spinner/info state before polling completes. (Tip: use a longer audio file, or a slower `WHISPER_MODEL`, to keep this state visible long enough to screenshot.) |
| 8 | `docs/screenshots/08-transcript.png` | `ResponseCard` → `TranscriptCard` | After processing completes — show the transcript text, detected language, word count, and duration. |
| 9 | `docs/screenshots/09-analysis.png` | `ResponseCard` → `AnalysisCard` | Same completed response as #8, scrolled to show all 5 scores, the strengths/weaknesses lists, and the detailed feedback paragraph. |

## After capturing

1. Place all 9 files in `docs/screenshots/` using the exact names above.
2. Optionally, replace the table in
   [README.md § Screenshots](../README.md#screenshots) with inline image
   embeds, e.g.:

   ```markdown
   ### Login
   ![Login page](docs/screenshots/01-login.png)
   ```

3. Remove the "Screenshots are not yet committed" note from the README once
   all 9 images are in place.
