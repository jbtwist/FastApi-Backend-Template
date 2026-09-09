/**
 * Failed sign-in, end to end.
 *
 * The frontend never renders text the backend wrote: it classifies the status
 * code and picks its own translated copy. Only a real cross-origin response
 * proves that wiring — a stubbed `fetch` cannot tell you the error path lost
 * its CORS headers, and a browser that cannot read the response reports a
 * network failure instead of the credentials error.
 */
import { button, emailField, expectOnSignIn, passwordField, register, submitSignIn } from '../fixtures/auth';
import { expect, test } from '../fixtures/test';

const BANNER = 'sign-in-form-message';

test('a wrong password shows the translated credentials error', async ({
  page,
  db,
  email,
  password,
}) => {
  await register(page, email, password);
  const token = await db.waitForOutboxToken(email, 'verification');
  await page.goto(`/verify-email-confirm?token=${encodeURIComponent(token)}`);
  await expect(page.getByText('Email verified')).toBeVisible();

  await submitSignIn(page, email, 'e2e-WrongPassw0rd');

  await expect(page.getByTestId(BANNER)).toHaveText('Email or password is incorrect.');
  await expectOnSignIn(page);
});

test('an unknown address shows the same error as a wrong password', async ({ page, email }) => {
  await submitSignIn(page, email, 'e2e-WrongPassw0rd');

  // Byte-identical to the wrong-password case: the screen must not become an
  // account-enumeration oracle.
  await expect(page.getByTestId(BANNER)).toHaveText('Email or password is incorrect.');
});

test('the password is cleared but the email is kept after a rejection', async ({
  page,
  email,
}) => {
  await submitSignIn(page, email, 'e2e-WrongPassw0rd');
  await expect(page.getByTestId(BANNER)).toBeVisible();

  await expect(emailField(page)).toHaveValue(email);
  await expect(passwordField(page)).toHaveValue('');
});

test('a malformed address is reported on the field, not as a banner', async ({ page }) => {
  await page.goto('/sign-in');
  await emailField(page).fill('not-an-email');
  await passwordField(page).fill('e2e-Passw0rd-2026');
  await button(page, 'Sign in').click();

  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByTestId(BANNER)).toBeHidden();
});
