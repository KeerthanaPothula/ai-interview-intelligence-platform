# Contributing

Thanks for considering a contribution. This project welcomes issues, bug
reports, and pull requests.

## Before you start

- For anything beyond a small fix, open an issue first (use the
  [bug report](../.github/ISSUE_TEMPLATE/bug_report.md) or
  [feature request](../.github/ISSUE_TEMPLATE/feature_request.md) template)
  so the approach can be discussed before you invest time in an
  implementation.
- Read [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — participation in this
  project means agreeing to it.
- For local setup, environment variables, and common commands, see
  [DEVELOPMENT.md](./DEVELOPMENT.md). For running the test suites, see
  [TESTING.md](./TESTING.md).

## Workflow

1. Fork the repo and create a branch off `main` (`git checkout -b
   feat/short-description`).
2. Make your change. Keep it focused — unrelated refactors or formatting-only
   diffs make a PR harder to review; open a separate PR for those.
3. Run the relevant checks locally before opening a PR (see
   [DEVELOPMENT.md § Common Commands](./DEVELOPMENT.md#common-commands)):
   - Backend: `ruff check .`, `black --check .`, `pytest`
   - Frontend: `npm run lint`, `npm run test`, `npm run build`
4. Open a PR against `main` using the
   [pull request template](../.github/pull_request_template.md). Link the
   issue it addresses (`Closes #123`) if one exists.
5. CI (`.github/workflows/ci.yml`, `.github/workflows/security.yml`) must
   pass — see [INFRASTRUCTURE.md](./INFRASTRUCTURE.md#cicd-github-actions)
   for what each job checks.

## Commit messages

This project loosely follows
[Conventional Commits](https://www.conventionalcommits.org/) prefixes
(`feat:`, `fix:`, `docs:`, `chore:`, `security:`, `refactor:`, `test:`) —
see [CHANGELOG.md](./CHANGELOG.md) for examples from this repo's own
history. A prefix is preferred but not enforced by CI.

## Code style

- **Backend**: formatted with `black` and linted with `ruff` (exact pinned
  versions are in `.github/workflows/ci.yml`); both run in CI and must pass
  with no errors.
- **Frontend**: linted with `eslint` (`npm run lint`); TypeScript strict
  mode is enabled (`tsc -b` runs as part of `npm run build` and fails the
  build on type errors).
- Match the existing code's conventions in the file you're editing over any
  personal preference — consistency within a module matters more than any
  single style rule.

## Tests

A change that fixes a bug or adds behavior should come with a test that
would have failed before the change. See [TESTING.md](./TESTING.md) for how
the existing backend (pytest + httpx, in-memory SQLite) and frontend
(Vitest + React Testing Library) suites are structured, and where coverage
is currently thin.

## Documentation

If your change affects an API endpoint, a database table, an environment
variable, or a deployment step, update the corresponding file in `docs/`
in the same PR — see [DEVELOPMENT.md](./DEVELOPMENT.md) for where each kind
of change is documented. Avoid duplicating an explanation that already
exists elsewhere; link to it instead.

---

## Maintainer reference: GitHub project setup

These are recommendations for keeping the project's GitHub presence (topics,
labels, milestones, releases) consistent — not something a contributor needs
to act on, but documented here so it isn't tribal knowledge.

### Repository topics

Recommended topics (Settings → General → Topics) so the repo surfaces in
the right GitHub searches: `fastapi`, `react`, `typescript`, `postgresql`,
`docker`, `ai`, `llm`, `gemini-api`, `whisper`, `interview-preparation`,
`machine-learning`, `python`, `vite`, `sqlalchemy`, `openai-whisper`.

### Labels

| Label | Color | Use for |
|---|---|---|
| `bug` | `#d73a4a` | Confirmed defect |
| `enhancement` | `#a2eeef` | New feature or improvement |
| `documentation` | `#0075ca` | Docs-only change |
| `good first issue` | `#7057ff` | Small, well-scoped, good for new contributors |
| `help wanted` | `#008672` | Maintainer is explicitly looking for outside help |
| `security` | `#b60205` | Vulnerability or hardening work — see [SECURITY.md](./SECURITY.md) |
| `infrastructure` | `#fbca04` | CI/CD, Docker, deployment |
| `needs-triage` | `#ededed` | Newly opened, not yet assessed |
| `wontfix` | `#ffffff` | Closed without action, with a reason recorded in the issue |

### Milestones

Group issues/PRs by theme rather than calendar date, mirroring how this
project actually evolved (see [CHANGELOG.md](./CHANGELOG.md)) — e.g.
`Voice Analytics`, `Live Interviews`, `Readiness Scoring`,
`Observability`, `Open Source Polish` — each closed when its issues are
resolved, rather than tied to a fixed deadline.

### Project board

A single board with columns `Triage → Backlog → In Progress → In Review →
Done` is sufficient at this project's size; split into multiple boards only
if backend and frontend work need independently visible queues.

### Versioning & releases

No version has been tagged yet. Recommended scheme going forward:
[Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **MAJOR** — breaking API or database-migration changes that require
  manual intervention to upgrade.
- **MINOR** — new endpoints/features, additive and backward-compatible
  (e.g. a new AI capability, a new optional field).
- **PATCH** — bug fixes, security patches, dependency bumps with no
  behavior change.

Tag releases on `main` (`git tag v1.0.0 && git push --tags`) and cut a
GitHub Release with notes summarizing the corresponding
[CHANGELOG.md](./CHANGELOG.md) entries since the previous tag.

## Related documentation

- [DEVELOPMENT.md](./DEVELOPMENT.md) — local setup and common commands.
- [TESTING.md](./TESTING.md) — running and writing tests.
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — community standards.
