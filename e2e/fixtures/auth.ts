/**
 * Page-level helpers for the auth screens.
 *
 * Selectors go through the accessible name wherever there is one — the fields
 * set `accessibilityLabel`, the buttons set `accessibilityRole="button"`, and
 * React Native Web turns both into ARIA. A test that can find the control the
 * way a screen reader does is also a test that fails when that affordance
 * regresses.
 */
import { expect, type Page } from '@playwright/test';

import type { Db } from './db';

/** Field labels, from `i18n/locales/en/common.json`. */
const EMAIL_LABEL = 'Email';
const PASSWORD_LABEL = 'Password';
const NEW_PASSWORD_LABEL = 'New password';

export function emailField(page: Page) {
  return page.getByLabel(EMAIL_LABEL, { exact: true });
}

export function passwordField(page: Page) {
  return page.getByLabel(PASSWORD_LABEL, { exact: true });
}

export function newPasswordField(page: Page) {
  return page.getByLabel(NEW_PASSWORD_LABEL, { exact: true });
}

export function button(page: Page, name: string) {
  return page.getByRole('button', { name, exact: true });
}

/**
 * Asserts the browser is in the signed-in area.
 *
 * The landmark is the placeholder home screen; when the product UI lands, this
 * is the one place that needs updating.
 */
export async function expectSignedIn(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText(/Welcome to\s+Expo/)).toBeVisible();
}

/** Asserts the browser is on the sign-in screen. */
export async function expectOnSignIn(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(button(page, 'Sign in')).toBeVisible();
}

/**
 * Matches `/verify-email`, with or without the `?email=` the sign-in screen
 * adds when it routes there.
 */
export const VERIFY_EMAIL_URL = /\/verify-email(\?|$)/;

/** Fills and submits the register form, leaving the browser on `/verify-email`. */
export async function register(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/register');
  await emailField(page).fill(email);
  await passwordField(page).fill(password);
  await button(page, 'Create account').click();
  await expect(page).toHaveURL(VERIFY_EMAIL_URL);
}

/** Opens the verification link for an already-registered address. */
export async function confirmEmail(page: Page, db: Db, email: string): Promise<void> {
  const token = await db.waitForOutboxToken(email, 'verification');
  await page.goto(`/verify-email-confirm?token=${encodeURIComponent(token)}`);
  await expect(page.getByText('Email verified')).toBeVisible();
}

/** Fills and submits the sign-in form. Does not assert the outcome. */
export async function submitSignIn(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/sign-in');
  await emailField(page).fill(email);
  await passwordField(page).fill(password);
  await button(page, 'Sign in').click();
}

/** Register, verify, sign in — the precondition for anything behind the session. */
export async function signUpAndSignIn(
  page: Page,
  db: Db,
  email: string,
  password: string,
): Promise<void> {
  await register(page, email, password);
  await confirmEmail(page, db, email);
  await submitSignIn(page, email, password);
  await expectSignedIn(page);
}
