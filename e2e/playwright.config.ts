/**
 * End-to-end configuration: the Expo web client, driven in a real browser,
 * against a real FastAPI + Postgres stack.
 *
 * Both servers are owned by Playwright. The backend gets `.env.e2e` (its own
 * database, no rate limiting, a 10-second access token); the web client gets
 * `EXPO_PUBLIC_API_URL` pointing at it. Nothing in `backend/` or `frontend/`
 * is modified to make this run — configuration reaches them through the
 * environment only.
 */
import { defineConfig, devices } from '@playwright/test';

import {
  backendEnv,
  backendPort,
  backendUrl,
  e2eRoot,
  frontendPort,
  frontendUrl,
} from './config/env';

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: './specs',
  // The suite drives real HTTP against a real database; a shared account or a
  // rotated refresh token makes parallel runs of the same spec ambiguous.
  // Files still run in parallel with each other.
  fullyParallel: false,
  workers: isCI ? 1 : undefined,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: isCI ? [['github'], ['html', { open: 'never' }]] : [['list'], ['html', { open: 'never' }]],

  // A 10-second access token plus a real network round trip; the default 30s
  // is tight for the refresh spec.
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: frontendUrl,
    // The UI is translated and the locale falls back to the browser's. Pin it
    // so assertions can name English copy.
    locale: 'en-US',
    timezoneId: 'UTC',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      command: 'bash scripts/start-backend.sh',
      cwd: e2eRoot,
      url: `${backendUrl}/health`,
      env: { ...backendEnv, E2E_BACKEND_PORT: backendPort },
      reuseExistingServer: !isCI,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: `npx expo start --web --port ${frontendPort}`,
      cwd: `${e2eRoot}/../frontend`,
      url: frontendUrl,
      env: {
        EXPO_PUBLIC_API_URL: backendUrl,
        // Keeps the Expo CLI non-interactive and stops it opening a browser of
        // its own alongside Playwright's.
        CI: '1',
        BROWSER: 'none',
      },
      reuseExistingServer: !isCI,
      // Metro's first web bundle is slow on a cold cache.
      timeout: 300_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
});
