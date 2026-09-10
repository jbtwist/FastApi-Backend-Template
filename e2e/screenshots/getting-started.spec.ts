/**
 * Captures the screenshots used by docs/getting-started/web-client.md.
 *
 * Run with `npm run screenshots`, not `npm test` — it writes PNGs into
 * `docs/assets/screenshots/`, and a normal test run has no business editing
 * the documentation. Re-run it after any change to the auth screens; a stale
 * screenshot is worse than none.
 *
 * It asserts as it goes, so a capture cannot silently record a broken screen.
 *
 * Unlike the specs, this uses one fixed address rather than a generated one:
 * a UUID in every screenshot reads badly. `deleteAccount` clears it first so
 * the walkthrough always starts from nothing.
 */
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { repoRoot } from '../config/env';
import {
  button,
  emailField,
  expectSignedIn,
  passwordField,
  VERIFY_EMAIL_URL,
} from '../fixtures/auth';
import { expect, test } from '../fixtures/test';

const EMAIL = 'ada@example.com';
const PASSWORD = 'correct-horse-battery';

const OUTPUT_DIR = join(repoRoot, 'docs/assets/screenshots');

/** Capture the auth card alone; the page around it is empty background. */
async function captureCard(page: Page, name: string): Promise<void> {
  await page
    .getByTestId('auth-screen-card')
    .screenshot({ path: join(OUTPUT_DIR, `${name}.png`), animations: 'disabled' });
}

test('capture the getting-started walkthrough', async ({ page, db }) => {
  await mkdir(OUTPUT_DIR, { recursive: true });
  await db.deleteAccount(EMAIL);

  await page.goto('/register');
  await emailField(page).fill(EMAIL);
  await passwordField(page).fill(PASSWORD);
  await captureCard(page, 'register');

  await button(page, 'Create account').click();
  await expect(page).toHaveURL(VERIFY_EMAIL_URL);
  await captureCard(page, 'verify-email');

  const token = await db.waitForOutboxToken(EMAIL, 'verification');
  await page.goto(`/verify-email-confirm?token=${encodeURIComponent(token)}`);
  await expect(page.getByText('Email verified')).toBeVisible();
  await captureCard(page, 'email-verified');

  await page.goto('/sign-in');
  await emailField(page).fill(EMAIL);
  await passwordField(page).fill(PASSWORD);
  await captureCard(page, 'sign-in');

  await button(page, 'Sign in').click();
  await expectSignedIn(page);
  await page.screenshot({
    path: join(OUTPUT_DIR, 'signed-in.png'),
    animations: 'disabled',
  });
});
