/**
 * T025 — `auth-context` state machine (RED).
 *
 * Exercises every transition in `data-model.md` → AuthSession:
 *   loading → signedIn | signedOut         (bootstrap)
 *   signedOut → signedIn                    (signIn)
 *   signedIn → signedOut                    (signOut)
 *   signedIn → expired → signedOut          (refresh failure — sets signedOutReason)
 *
 * Transport is a queued `fetch` mock (FIFO, url-agnostic) plus the in-memory
 * `expo-secure-store` fake, so the provider is driven purely through
 * `api-client` / `auth-api` against the `contracts/auth-api.md` shapes.
 */
import { Platform } from 'react-native';
import { act, renderHook, waitFor } from '@testing-library/react-native';

import { configureApiClient, resetApiClient } from './api-client';
import { AuthProvider, useAuth } from './auth-context';
import { mockFetch, secureStoreSnapshot, seedSecureStore, type MockFetch } from '@/test-utils';

const BASE = 'https://api.test';
const ACCESS_KEY = 'auth.accessToken';
const REFRESH_KEY = 'auth.refreshToken';

const originalOS = Platform.OS;
function setPlatform(os: typeof Platform.OS) {
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
}

const USER = { id: 'u1', email: 'a@b.c', email_verified: true };
const LOGIN_OK = { ...USER, access_token: 'acc-2', refresh_token: 'ref-2', token_type: 'bearer' };
const REFRESH_OK = { access_token: 'acc-3', refresh_token: 'ref-3', token_type: 'bearer' };

let fetchMock: MockFetch;

function mountAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider });
}

beforeEach(() => {
  resetApiClient();
  configureApiClient({ baseUrl: BASE, platform: 'native', timeoutMs: 1_000 });
  fetchMock = mockFetch();
});

afterEach(() => {
  fetchMock.restore();
  resetApiClient();
  setPlatform(originalOS);
  jest.restoreAllMocks();
});

describe('bootstrap — native', () => {
  beforeEach(() => setPlatform('ios'));

  it('starts in loading and lands on signedIn when a stored session validates', async () => {
    seedSecureStore({ [ACCESS_KEY]: 'acc-1', [REFRESH_KEY]: 'ref-1' });
    fetchMock.queueJson(200, USER);

    const { result } = mountAuth();
    expect(result.current.status).toBe('loading');

    await waitFor(() => expect(result.current.status).toBe('signedIn'));
    expect(result.current.user).toEqual({ id: 'u1', email: 'a@b.c', emailVerified: true });
    expect(result.current.signedOutReason).toBeNull();
  });

  it('goes straight to signedOut with no network call when no tokens are stored', async () => {
    const { result } = mountAuth();

    await waitFor(() => expect(result.current.status).toBe('signedOut'));
    expect(fetchMock.requests).toHaveLength(0);
    expect(result.current.user).toBeNull();
    expect(result.current.signedOutReason).toBeNull();
  });

  it('treats a partial/corrupt stored pair as no session (no network call)', async () => {
    seedSecureStore({ [ACCESS_KEY]: 'orphan-access' });

    const { result } = mountAuth();

    await waitFor(() => expect(result.current.status).toBe('signedOut'));
    expect(fetchMock.requests).toHaveLength(0);
    expect(secureStoreSnapshot()).toEqual({});
  });

  it('recovers via a transparent refresh when /me returns 401', async () => {
    seedSecureStore({ [ACCESS_KEY]: 'acc-1', [REFRESH_KEY]: 'ref-1' });
    fetchMock
      .queueJson(401, { detail: 'Not authenticated' })
      .queueJson(200, REFRESH_OK)
      .queueJson(200, USER);

    const { result } = mountAuth();

    await waitFor(() => expect(result.current.status).toBe('signedIn'));
    expect(result.current.user).toEqual({ id: 'u1', email: 'a@b.c', emailVerified: true });
    expect(secureStoreSnapshot()).toEqual({ [ACCESS_KEY]: 'acc-3', [REFRESH_KEY]: 'ref-3' });
  });

  it('clears a dead session and shows no notice when the refresh also fails', async () => {
    seedSecureStore({ [ACCESS_KEY]: 'acc-1', [REFRESH_KEY]: 'ref-1' });
    fetchMock
      .queueJson(401, { detail: 'Not authenticated' })
      .queueJson(401, { detail: 'Not authenticated' });

    const { result } = mountAuth();

    await waitFor(() => expect(result.current.status).toBe('signedOut'));
    expect(result.current.signedOutReason).toBeNull();
    expect(secureStoreSnapshot()).toEqual({});
  });
});

describe('bootstrap — web', () => {
  beforeEach(() => {
    setPlatform('web');
    configureApiClient({ platform: 'web' });
  });

  it('calls /me directly (no token store) and signs in on 200', async () => {
    fetchMock.queueJson(200, USER);

    const { result } = mountAuth();

    await waitFor(() => expect(result.current.status).toBe('signedIn'));
    expect(result.current.user).toEqual({ id: 'u1', email: 'a@b.c', emailVerified: true });
    expect(fetchMock.requests).toHaveLength(1);
    expect(fetchMock.requests[0].url).toBe(`${BASE}/auth/me`);
  });

  it('is signedOut when /me and the follow-up refresh both 401', async () => {
    fetchMock.queueJson(401, { detail: 'Not authenticated' }).queueJson(401, { detail: 'Not authenticated' });

    const { result } = mountAuth();

    await waitFor(() => expect(result.current.status).toBe('signedOut'));
    expect(result.current.signedOutReason).toBeNull();
  });
});

describe('signIn — native', () => {
  beforeEach(() => setPlatform('ios'));

  async function mountSignedOut() {
    const view = mountAuth();
    await waitFor(() => expect(view.result.current.status).toBe('signedOut'));
    return view;
  }

  it('persists the token pair and moves to signedIn on 200', async () => {
    const { result } = await mountSignedOut();
    fetchMock.queueJson(200, LOGIN_OK);

    await act(async () => {
      await result.current.signIn('a@b.c', 'pw-123456789012');
    });

    expect(result.current.status).toBe('signedIn');
    expect(result.current.user).toEqual({ id: 'u1', email: 'a@b.c', emailVerified: true });
    expect(secureStoreSnapshot()).toEqual({ [ACCESS_KEY]: 'acc-2', [REFRESH_KEY]: 'ref-2' });
  });

  it('rethrows invalid-credentials and stays signedOut, storing nothing', async () => {
    const { result } = await mountSignedOut();
    fetchMock.queueJson(401, { detail: 'Invalid credentials' });

    await expect(
      act(async () => {
        await result.current.signIn('a@b.c', 'wrong');
      }),
    ).rejects.toMatchObject({ uiError: { kind: 'invalid-credentials' } });

    expect(result.current.status).toBe('signedOut');
    expect(secureStoreSnapshot()).toEqual({});
  });

  it('rethrows email-not-verified (with the submitted email) and stays signedOut', async () => {
    const { result } = await mountSignedOut();
    fetchMock.queueJson(403, { detail: 'Email not verified' });

    await expect(
      act(async () => {
        await result.current.signIn('a@b.c', 'pw-123456789012');
      }),
    ).rejects.toMatchObject({ uiError: { kind: 'email-not-verified', email: 'a@b.c' } });

    expect(result.current.status).toBe('signedOut');
  });

  it('clears a prior signedOutReason on a fresh successful sign-in', async () => {
    seedSecureStore({ [ACCESS_KEY]: 'acc-1', [REFRESH_KEY]: 'ref-1' });
    fetchMock.queueJson(200, USER);
    const { result } = mountAuth();
    await waitFor(() => expect(result.current.status).toBe('signedIn'));

    // kill the session via a failing refresh
    fetchMock.queueJson(401, { detail: 'Not authenticated' });
    await act(async () => {
      await result.current.refreshSession();
    });
    expect(result.current.status).toBe('signedOut');
    expect(result.current.signedOutReason).toBe('session-expired');

    fetchMock.queueJson(200, LOGIN_OK);
    await act(async () => {
      await result.current.signIn('a@b.c', 'pw-123456789012');
    });
    expect(result.current.status).toBe('signedIn');
    expect(result.current.signedOutReason).toBeNull();
  });
});

describe('register — native', () => {
  beforeEach(() => setPlatform('ios'));

  async function mountSignedOut() {
    const view = mountAuth();
    await waitFor(() => expect(view.result.current.status).toBe('signedOut'));
    return view;
  }

  it('resolves on 204 without signing in or storing tokens', async () => {
    const { result } = await mountSignedOut();
    fetchMock.queueResponse({ status: 204 });

    await act(async () => {
      await result.current.register('new@b.c', 'pw-123456789012');
    });

    expect(result.current.status).toBe('signedOut');
    expect(secureStoreSnapshot()).toEqual({});
  });

  it('rethrows a password-policy error on 422', async () => {
    const { result } = await mountSignedOut();
    fetchMock.queueJson(422, { detail: 'Password is too short (minimum 12 characters)' });

    await expect(
      act(async () => {
        await result.current.register('new@b.c', 'short');
      }),
    ).rejects.toMatchObject({ uiError: { kind: 'password-policy' } });
  });
});

describe('signOut — native', () => {
  beforeEach(() => setPlatform('ios'));

  async function mountSignedIn() {
    seedSecureStore({ [ACCESS_KEY]: 'acc-1', [REFRESH_KEY]: 'ref-1' });
    fetchMock.queueJson(200, USER);
    const view = mountAuth();
    await waitFor(() => expect(view.result.current.status).toBe('signedIn'));
    return view;
  }

  it('calls logout, clears the store and returns to signedOut', async () => {
    const { result } = await mountSignedIn();
    fetchMock.queueResponse({ status: 204 });

    await act(async () => {
      await result.current.signOut();
    });

    expect(result.current.status).toBe('signedOut');
    expect(result.current.user).toBeNull();
    expect(result.current.signedOutReason).toBeNull();
    expect(secureStoreSnapshot()).toEqual({});
  });

  it('still clears locally when the logout call fails', async () => {
    const { result } = await mountSignedIn();
    fetchMock.queueNetworkError();

    await act(async () => {
      await result.current.signOut();
    });

    expect(result.current.status).toBe('signedOut');
    expect(secureStoreSnapshot()).toEqual({});
  });
});

describe('refreshSession — native', () => {
  beforeEach(() => setPlatform('ios'));

  async function mountSignedIn() {
    seedSecureStore({ [ACCESS_KEY]: 'acc-1', [REFRESH_KEY]: 'ref-1' });
    fetchMock.queueJson(200, USER);
    const view = mountAuth();
    await waitFor(() => expect(view.result.current.status).toBe('signedIn'));
    return view;
  }

  it('rotates the pair and stays signedIn on refresh 200', async () => {
    const { result } = await mountSignedIn();
    fetchMock.queueJson(200, REFRESH_OK);

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.refreshSession();
    });

    expect(ok).toBe(true);
    expect(result.current.status).toBe('signedIn');
    expect(secureStoreSnapshot()).toEqual({ [ACCESS_KEY]: 'acc-3', [REFRESH_KEY]: 'ref-3' });
  });

  it('goes signedIn → expired → signedOut with a one-shot notice on refresh 401', async () => {
    const { result } = await mountSignedIn();
    fetchMock.queueJson(401, { detail: 'Not authenticated' });

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.refreshSession();
    });

    expect(ok).toBe(false);
    expect(result.current.status).toBe('signedOut');
    expect(result.current.user).toBeNull();
    expect(result.current.signedOutReason).toBe('session-expired');
    expect(secureStoreSnapshot()).toEqual({});
  });
});

describe('useAuth outside a provider', () => {
  it('throws a helpful error', () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/);
    spy.mockRestore();
  });
});
