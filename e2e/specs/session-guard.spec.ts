/**
 * Which routes the session gate opens and which it closes.
 *
 * The signed-in area has no sign-out control yet — `signOut` is currently only
 * reachable from the verify-email and reset-password conflict prompts — so
 * logout here goes through the API on the page's own cookie jar. Swap it for a
 * button press once the product UI has one.
 */
import { backendUrl } from '../config/env';
import {
  button,
  expectOnSignIn,
  expectSignedIn,
  newPasswordField,
  refreshCookie,
  signUpAndSignIn,
} from '../fixtures/auth';
import { expect, test } from '../fixtures/test';

test('the signed-in area redirects a visitor with no session', async ({ page }) => {
  await page.goto('/');

  await expectOnSignIn(page);
});

test('logout clears both cookies and closes the signed-in area', async ({
  page,
  db,
  email,
  password,
}) => {
  await signUpAndSignIn(page, db, email, password);

  const response = await page.request.post(`${backendUrl}/auth/logout`);
  expect(response.status()).toBe(204);

  const names = (await page.context().cookies()).map((c) => c.name);
  expect(names).not.toContain('access_token');
  expect(names).not.toContain('refresh_token');

  await page.goto('/');
  await expectOnSignIn(page);
});

test('logout revokes the refresh token server-side, not just the cookie', async ({
  page,
  request,
  db,
  email,
  password,
}) => {
  await signUpAndSignIn(page, db, email, password);
  // Captured while the session is live, standing in for a token someone else
  // already has. Clearing the cookie would not take it away from them.
  const captured = await refreshCookie(page);
  expect(captured).toBeTruthy();

  await page.request.post(`${backendUrl}/auth/logout`);

  // `request` has its own cookie jar, so the captured token is the only
  // credential in play.
  const replay = await request.post(`${backendUrl}/auth/refresh`, {
    data: { refresh_token: captured },
  });
  expect(replay.status()).toBe(401);
});

test('a session survives a reload', async ({ page, db, email, password }) => {
  await signUpAndSignIn(page, db, email, password);

  await page.reload();

  await expectSignedIn(page);
});

test('the emailed links open without a session', async ({ page }) => {
  // Both are top-level routes on purpose: a cold start straight from the inbox
  // has no session, and gating them would strand the user.
  //
  // reset-password takes the token on trust and only finds out it is bad on
  // submit, so reaching the form is the assertion here.
  await page.goto('/reset-password?token=not-a-real-token');
  await expect(page.getByText('Set a new password')).toBeVisible();

  await page.goto('/verify-email-confirm');
  await expect(page.getByText('This verification link is missing its token.')).toBeVisible();
});

test('a reset link with a bad token fails on submit, not on arrival', async ({ page }) => {
  await page.goto('/reset-password?token=not-a-real-token');

  await newPasswordField(page).fill('e2e-Passw0rd-2026');
  await button(page, 'Save new password').click();

  await expect(page.getByText('This link is invalid or expired')).toBeVisible();
});
