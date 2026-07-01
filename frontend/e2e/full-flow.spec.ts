import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RESUME_FIXTURE = path.join(__dirname, 'fixtures', 'sample-resume.pdf');
const AUDIO_FIXTURE = path.join(__dirname, 'fixtures', 'sample-response.wav');

// Genuinely end-to-end: drives a real browser against the real frontend dev
// server, the real FastAPI backend, a real Postgres database, real Whisper
// transcription, and real Gemini calls. No network mocking. See
// docs/TESTING.md for prerequisites — this is a local/manual verification
// step, not part of the CI gate (CI has no GEMINI_API_KEY secret).
test('register, login, upload resume, generate questions, interview, report, dashboard', async ({
  page,
}) => {
  const unique = Date.now();
  const email = `e2e-${unique}@example.com`;
  const password = 'correct-horse-battery-staple';

  // --- Register -------------------------------------------------------
  await page.goto('/register');
  await page.getByLabel('Full name').fill('E2E Test User');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Register' }).click();
  await expect(page.getByRole('heading', { name: 'Account created' })).toBeVisible();
  await page.getByRole('link', { name: 'Go to login' }).click();

  // --- Login ------------------------------------------------------------
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page).toHaveURL('/');

  // --- Upload resume ------------------------------------------------------
  await expect(page.getByText('No resume uploaded yet.')).toBeVisible();
  await page.getByLabel('Resume file').setInputFiles(RESUME_FIXTURE);
  await page.getByRole('button', { name: 'Upload Resume' }).click();
  await expect(page.getByText(/Current resume:/)).toBeVisible({ timeout: 15_000 });

  // --- Create interview session --------------------------------------
  const sessionTitle = `E2E Session ${unique}`;
  await page.getByLabel('Title').fill(sessionTitle);
  await page.getByLabel('Job role').fill('Backend Engineer');
  await page
    .getByLabel('Job description')
    .fill('Builds and maintains backend services using Python, FastAPI, and PostgreSQL.');
  await page.getByRole('button', { name: 'Create Session' }).click();
  await page.getByRole('link', { name: new RegExp(sessionTitle) }).click();
  await expect(page).toHaveURL(/\/sessions\/.+/);

  // --- Generate questions -----------------------------------------------
  await page.getByRole('button', { name: 'Generate Questions' }).click();
  await expect(page.locator('.question-card').first()).toBeVisible({ timeout: 30_000 });

  // --- Interview: upload an audio response to the first question --------
  const firstQuestion = page.locator('.question-card').first();
  await firstQuestion.locator('input[type="file"]').setInputFiles(AUDIO_FIXTURE);
  await firstQuestion.getByRole('button', { name: 'Upload Recording' }).click();

  // Real Whisper transcription + real Gemini analysis run asynchronously —
  // give this a generous timeout.
  await expect(firstQuestion.getByText('Completed')).toBeVisible({ timeout: 120_000 });
  await expect(firstQuestion.getByTestId('analysis-card')).toBeVisible({ timeout: 30_000 });

  // --- Generate report ----------------------------------------------------
  await page.getByRole('button', { name: 'Generate Report' }).click();
  await expect(page.getByText('Final Score')).toBeVisible({ timeout: 60_000 });

  // --- Dashboard ----------------------------------------------------------
  await page.getByRole('link', { name: 'Dashboard' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText('Total Sessions')).toBeVisible();
});
