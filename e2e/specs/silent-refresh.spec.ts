/**
 * Session renewal against a real cookie jar.
 *
 * `api-client` coalesces concurrent 401s onto a single `POST /auth/refresh`
 * and retries the original request. Nothing below this layer can check it: the
 * refresh cookie is httponly and scoped to `/auth`, it rotates on every use,
 * and reuse revokes the whole family. Those are browser and server behaviours,
 * not client-code behaviours.
 *
 * `ACCESS_TOKEN_EXP` is 10 seconds in `.env.e2e` so these run in real time.
 */
import { accessTokenExpSeconds, backendUrl } from '../config/env';
import { expectOnSignIn, expectSignedIn, signUpAndSignIn } from '../fixtures/auth';
import { expect, test } from '../fixtures/test';

/** Long enough that the access token is certainly stale. */
const PAST_EXPIRY_MS = (accessTokenExpSeconds + 2) * 1000;

async function refreshCookie(page: import('@playwright/test').Page): Promise<string | undefined> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === 'refresh_token')?.value;
}

test('an expired access token is renewed without signing the user out', async ({
  page,
  db,
  email,
  password,
}) => {
  await signUpAndSignIn(page, db, email, password);
  const before = await refreshCookie(page);
  expect(before).toBeTruthy();

  await page.waitForTimeout(PAST_EXPIRY_MS);
  await page.reload();

  // The launch probe hits `/me`, takes a 401, refreshes, and retries.
  await expectSignedIn(page);

  const after = await refreshCookie(page);
  expect(after).toBeTruthy();
  expect(after).not.toBe(before);
});

/**
 * Signs in, rotates once, and hands back the now-spent token together with its
 * live successor.
 */
async function rotateOnce(
  page: import('@playwright/test').Page,
  db: import('../fixtures/db').Db,
  email: string,
  password: string,
): Promise<{ spent: string; live: string }> {
  await signUpAndSignIn(page, db, email, password);
  const spent = await refreshCookie(page);
  expect(spent).toBeTruthy();

  await page.waitForTimeout(PAST_EXPIRY_MS);
  await page.reload();
  await expectSignedIn(page);

  const live = await refreshCookie(page);
  expect(live).toBeTruthy();
  expect(live).not.toBe(spent);
  return { spent: spent as string, live: live as string };
}

test('a spent refresh token is rejected on replay', async ({
  page,
  request,
  db,
  email,
  password,
}) => {
  const { spent } = await rotateOnce(page, db, email, password);

  // `request` has its own cookie jar, so the body is the only token in play
  // and the browser's session is not disturbed by the call.
  const replay = await request.post(`${backendUrl}/auth/refresh`, {
    data: { refresh_token: spent },
  });

  expect(replay.status()).toBe(401);
});

test('replaying a spent refresh token revokes the whole family', async ({
  page,
  request,
  db,
  email,
  password,
}) => {
  const { spent } = await rotateOnce(page, db, email, password);

  await request.post(`${backendUrl}/auth/refresh`, { data: { refresh_token: spent } });

  // The successor is still in the browser and its access token is still fresh,
  // so only the next renewal can reveal the revocation.
  await page.waitForTimeout(PAST_EXPIRY_MS);
  await page.reload();

  await expectOnSignIn(page);
});
