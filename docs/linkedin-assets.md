# LinkedIn Assets

Three posts for different stages of sharing this project. Post them on
different days rather than all at once — spacing them out gives each one
its own visibility window. Replace `[link]` with the GitHub repo URL (and a
live demo URL if/when one exists).

---

## 1. Launch Post

Use when first announcing the finished project.

> I just finished building an AI Interview Intelligence Platform — a
> full-stack app for practicing job interviews and getting structured,
> AI-generated feedback.
>
> How it works:
> - You create an interview session for a target job role
> - Google Gemini generates a set of role-specific interview questions
> - You record/upload an audio answer for each question
> - OpenAI Whisper transcribes the audio on the server
> - Gemini evaluates the transcript across 5 dimensions — communication,
>   technical depth, problem solving, confidence, and overall — with
>   written strengths, weaknesses, and detailed feedback
>
> Tech stack: FastAPI, SQLAlchemy, PostgreSQL, and Alembic on the backend;
> React, TypeScript, and Vite on the frontend; JWT authentication;
> Dockerized and deployed to Render.
>
> It also has a 108-test automated suite (94 backend, 14 frontend) covering
> auth, per-user data ownership, and the async processing pipeline.
>
> Code, architecture diagrams, and deployment docs are here: [link]
>
> Would love feedback from anyone who's built something similar, or anyone
> who's interviewing and wants to try it out.
>
> #softwareengineering #fastapi #react #buildinpublic #ai

---

## 2. Technical Deep Dive Post

Use a couple of weeks after the launch post, once it's had time to circulate.
Focuses on the asynchronous processing pipeline — a meaty design topic that
shows systems thinking, not just "I called an API."

> One design problem I spent real time on while building my AI Interview
> Intelligence Platform: what happens to an uploaded audio file between
> "uploaded" and "here's your transcript and score"?
>
> The naive approach — call Whisper, then call Gemini, then return the
> result in the same request — doesn't work. Whisper transcription can take
> longer than an HTTP request should reasonably block for, and either step
> can fail or time out.
>
> So I modeled it as an explicit state machine on the `AudioResponse`
> record:
>
> uploaded -> processing -> completed
>                       \-> failed
>
> A background task picks up "uploaded" responses, transitions them to
> "processing," runs Whisper (bounded by a configurable timeout), then sends
> the transcript to Gemini for scoring (also bounded, with the transcript
> truncated to a max length before the API call). On success it writes the
> transcript and analysis and marks "completed." On any failure — timeout,
> API error, anything — it marks "failed" with a generic, user-safe error
> message. Raw exception text never reaches the client.
>
> One edge case that's easy to miss: what if the server crashes or restarts
> while a job is "processing"? Without handling this, that response is stuck
> forever — neither failed nor retryable. I added a startup check that finds
> any response still marked "processing" and recovers it to "failed" so the
> user can retry.
>
> On the frontend, this maps to a simple polling hook — every 3 seconds,
> check the status, stop polling once it's "completed" or "failed," then
> fetch the transcript and analysis only when they're actually ready.
>
> None of this is exotic, but getting the state machine and failure modes
> right up front made the rest of the feature — and the test suite for it —
> much simpler to build.
>
> Full write-up and diagrams: [link]
>
> #systemdesign #backenddevelopment #python #fastapi

---

## 3. Learning Journey Post

Use a few weeks after the technical deep dive — more personal/reflective,
good for engagement and for showing growth to recruiters who read further
than the headline.

> Some honest reflections after finishing my AI Interview Intelligence
> Platform project.
>
> What I expected to be the hard part: integrating two different AI
> services (Whisper for transcription, Gemini for evaluation). It was real
> work, but it was the *predictable* kind — read the docs, handle the
> response format, add timeouts.
>
> What actually took the most thought:
>
> - **Authorization, not authentication.** Logging users in was easy. Making
>   sure User A can never see, modify, or even detect the existence of User
>   B's sessions took more care — every single query needed an ownership
>   check, and I had to decide between 403 ("forbidden") and 404 ("not
>   found") for other users' resources. I went with 404 everywhere, so the
>   API doesn't leak which resource IDs exist.
>
> - **Designing for failure, not just success.** It's easy to build the
>   "transcription succeeds, evaluation succeeds" path. It's much less
>   obvious, until you sit with it, that you also need: what if Whisper times
>   out? What if Gemini's response doesn't parse? What if the server restarts
>   mid-job? I ended up with as much logic for failure states as for success
>   states.
>
> - **Numeric precision matters more than I expected.** AI evaluation scores
>   are floats, but storing and comparing floats in a database can introduce
>   tiny rounding errors. Using `NUMERIC` columns with Python's `Decimal`
>   type (instead of raw floats) avoided a class of subtle bugs I didn't
>   anticipate going in.
>
> - **Documentation is part of the deliverable.** Writing the Render
>   deployment guide forced me to actually verify every environment variable
>   and step, which caught a couple of issues I'd have otherwise hit during a
>   real deploy.
>
> If you're working on something similar — especially the
> "upload-then-process-asynchronously" pattern — happy to compare notes.
>
> Repo: [link]
>
> #buildinpublic #careerdevelopment #softwareengineering #learningjourney
