import { defineConfig, devices } from '@playwright/test';

// Real, unmocked E2E suite: drives the actual frontend dev server against a
// real running backend (real Postgres, real Gemini calls). It is a local/
// manual verification step, not part of the CI gate — see docs/TESTING.md.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Bypass any system-wide TLS-intercepting proxy (e.g. Avast Web Shield)
        // so the headless browser can reach localhost:8000 directly.
        launchOptions: { args: ['--no-proxy-server'] },
      },
    },
  ],
});
