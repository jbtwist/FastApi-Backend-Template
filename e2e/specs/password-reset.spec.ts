/**
 * Forgotten password, end to end: the request form, the outbox row, the
 * emailed link, the new password, and the old one going dead.
 */
import {
  button,
  confirmEmail,
  emailField,
  expectSignedIn,
  newPasswordField,
  register,
  submitSignIn,
} from '../fixtures/auth';
import { expect, test } from '../fixtures/test';

const NEW_PASSWORD = 'e2e-Rotated-2026';

async function requestReset(page: import('@playwright/test').Page, email: string): Promise<void> {
  await page.goto('/forgot-password');
  await emailField(page).fill(email);
  await button(page, 'Send reset link').click();
  await expect(page.getByText('Check your email')).toBeVisible();
}

test('a reset link sets a new password and retires the old one', async ({
  page,
  db,
  email,
  password,
}) => {
  await register(page, email, password);
  await confirmEmail(page, db, email);

  await requestReset(page, email);
  const token = await db.waitForOutboxToken(email, 'password_reset');

  await page.goto(`/reset-password?token=${encodeURIComponent(token)}`);
  await newPasswordField(page).fill(NEW_PASSWORD);
  await button(page, 'Save new password').click();
  await expect(page.getByText('Password updated')).toBeVisible();

  await submitSignIn(page, email, NEW_PASSWORD);
  await expectSignedIn(page);
});

test('the old password stops working once the reset lands', async ({
  page,
  db,
  email,
  password,
}) => {
  await register(page, email, password);
  await confirmEmail(page, db, email);

  await requestReset(page, email);
  const token = await db.waitForOutboxToken(email, 'password_reset');
  await page.goto(`/reset-password?token=${encodeURIComponent(token)}`);
  await newPasswordField(page).fill(NEW_PASSWORD);
  await button(page, 'Save new password').click();
  await expect(page.getByText('Password updated')).toBeVisible();

  await submitSignIn(page, email, password);

  await expect(page.getByTestId('sign-in-form-message')).toHaveText(
    'Email or password is incorrect.',
  );
});

test('a reset token cannot be spent twice', async ({ page, db, email, password }) => {
  await register(page, email, password);
  await confirmEmail(page, db, email);

  await requestReset(page, email);
  const token = await db.waitForOutboxToken(email, 'password_reset');
  const link = `/reset-password?token=${encodeURIComponent(token)}`;

  await page.goto(link);
  await newPasswordField(page).fill(NEW_PASSWORD);
  await button(page, 'Save new password').click();
  await expect(page.getByText('Password updated')).toBeVisible();

  await page.goto(link);
  await newPasswordField(page).fill('e2e-Different-2026');
  await button(page, 'Save new password').click();

  await expect(page.getByText('This link is invalid or expired')).toBeVisible();
});

test('an unknown address is answered exactly like a known one', async ({ page, email }) => {
  await requestReset(page, email);

  // The screen must say the same thing either way; anything else leaks which
  // addresses have accounts.
  await expect(
    page.getByText('If that address has an account, a reset link is on its way.'),
  ).toBeVisible();
});
