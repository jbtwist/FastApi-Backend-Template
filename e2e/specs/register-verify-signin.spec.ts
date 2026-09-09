/**
 * The full path from nothing to a signed-in session, across both apps: the
 * register form, the outbox row it commits, the emailed confirm link, and the
 * sign-in that the confirmation unlocks.
 */
import {
  button,
  confirmEmail,
  emailField,
  expectSignedIn,
  passwordField,
  register,
  submitSignIn,
  VERIFY_EMAIL_URL,
} from '../fixtures/auth';
import { expect, test } from '../fixtures/test';

test('a new account registers, verifies by link, and signs in', async ({
  page,
  db,
  email,
  password,
}) => {
  await register(page, email, password);
  await expect(page.getByText('Verify your email')).toBeVisible();
  expect(await db.isEmailVerified(email)).toBe(false);

  await confirmEmail(page, db, email);
  expect(await db.isEmailVerified(email)).toBe(true);

  await button(page, 'Continue').click();
  await submitSignIn(page, email, password);
  await expectSignedIn(page);
});

test('signing in before verifying lands on the verify screen', async ({
  page,
  email,
  password,
}) => {
  await register(page, email, password);

  await submitSignIn(page, email, password);

  // A 403 on login is the "account exists but is unverified" case, and the
  // screen routes rather than showing a banner, carrying the address so the
  // verify screen can name it.
  await expect(page).toHaveURL(VERIFY_EMAIL_URL);
  await expect(page.getByText('Verify your email')).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
});

test('registering an address that already has an account changes nothing', async ({
  page,
  db,
  email,
  password,
}) => {
  await register(page, email, password);
  await db.waitForOutboxToken(email, 'verification');
  expect(await db.countOutboxEntries(email, 'verification')).toBe(1);

  // Same address, different password. The screen must not betray that the
  // account exists, and the second attempt must not touch it.
  await register(page, email, 'e2e-Impostor-2026');

  expect(await db.countOutboxEntries(email, 'verification')).toBe(1);
  await confirmEmail(page, db, email);
  await submitSignIn(page, email, password);
  await expectSignedIn(page);
});

test('a verification link that was never issued is rejected', async ({ page }) => {
  await page.goto('/verify-email-confirm?token=not-a-real-token');

  await expect(page.getByText('This link is invalid or expired')).toBeVisible();
  await expect(button(page, 'Request a new email')).toBeVisible();
});

test('the register form rejects a password under the policy floor', async ({ page, email }) => {
  await page.goto('/register');
  await emailField(page).fill(email);
  await passwordField(page).fill('short');
  await button(page, 'Create account').click();

  // Client-side, so the request never leaves; the assertion is that the user
  // is still on the form with something to fix.
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole('alert')).toBeVisible();
});
