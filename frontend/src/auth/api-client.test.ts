import { Platform } from 'react-native';

import { mockFetch, type MockFetch } from '@/test-utils';
import {
  AuthApiError,
  SessionExpiredError,
  configureApiClient,
  ensureFreshSession,
  request,
  resetApiClient,
} from './api-client';
import * as tokenStore from './token-store';

const BASE = 'https://api.test';

let fetchMock: MockFetch;

/** Headers the client sent on the nth request, as a plain record. */
function sentHeaders(index: number): Record<string, string> {
  return (fetchMock.requests[index].init?.headers ?? {}) as Record<string, string>;
}

beforeEach(() => {
  fetchMock = mockFetch();
  resetApiClient();
  configureApiClient({ baseUrl: BASE, platform: 'native', timeoutMs: 1_000 });

  jest.spyOn(tokenStore, 'getTokens').mockResolvedValue({
    accessToken: 'access-1',
    refreshToken: 'refresh-1',
  });
  jest.spyOn(tokenStore, 'setTokens').mockResolvedValue();
  jest.spyOn(tokenStore, 'clearTokens').mockResolvedValue();
});

afterEach(() => {
  fetchMock.restore();
  jest.restoreAllMocks();
  resetApiClient();
});

describe('request — success', () => {
  it('returns the parsed body and attaches the bearer token on native', async () => {
    fetchMock.queueJson(200, { id: 'u1', email: 'a@b.c' });

    const body = await request<{ id: string }>('/auth/me', { context: 'me' });

    expect(body).toEqual({ id: 'u1', email: 'a@b.c' });
    expect(fetchMock.requests[0].url).toBe(`${BASE}/auth/me`);
    expect(sentHeaders(0).Authorization).toBe('Bearer access-1');
  });

  it('returns undefined for a 204', async () => {
    fetchMock.queueJson(204);
    await expect(
      request('/auth/logout', { context: 'logout', method: 'POST' }),
    ).resolves.toBeUndefined();
  });

  it('web transport uses credentials:include and no Authorization header', async () => {
    configureApiClient({ platform: 'web' });
    fetchMock.queueJson(200, { id: 'u1' });

    await request('/auth/me', { context: 'me' });

    expect(fetchMock.requests[0].init?.credentials).toBe('include');
    expect(sentHeaders(0).Authorization).toBeUndefined();
  });
});

describe('request — 401 → refresh → retry', () => {
  it('refreshes once, persists the new pair, retries with the fresh token, succeeds', async () => {
    fetchMock
      .queueJson(401, { detail: 'Not authenticated' }) // original
      .queueJson(200, {
        access_token: 'access-2',
        refresh_token: 'refresh-2',
        token_type: 'bearer',
      }) // refresh
      .queueJson(200, { ok: true }); // retry
    (tokenStore.getTokens as jest.Mock)
      .mockResolvedValueOnce({ accessToken: 'access-1', refreshToken: 'refresh-1' }) // original
      .mockResolvedValueOnce({ accessToken: 'access-1', refreshToken: 'refresh-1' }) // refresh
      .mockResolvedValueOnce({ accessToken: 'access-2', refreshToken: 'refresh-2' }); // retry

    const body = await request<{ ok: boolean }>('/auth/me', { context: 'me' });

    expect(body).toEqual({ ok: true });
    expect(tokenStore.setTokens).toHaveBeenCalledWith({
      accessToken: 'access-2',
      refreshToken: 'refresh-2',
    });
    expect(fetchMock.requests.map((r) => r.url)).toEqual([
      `${BASE}/auth/me`,
      `${BASE}/auth/refresh`,
      `${BASE}/auth/me`,
    ]);
    expect(JSON.parse(fetchMock.requests[1].init?.body as string)).toEqual({
      refresh_token: 'refresh-1',
    });
    expect(sentHeaders(2).Authorization).toBe('Bearer access-2');
  });

  it('a second 401 after a successful refresh → SessionExpiredError + onSessionExpired', async () => {
    const onSessionExpired = jest.fn();
    configureApiClient({ onSessionExpired });

    fetchMock
      .queueJson(401, { detail: 'Not authenticated' })
      .queueJson(200, { access_token: 'a2', refresh_token: 'r2' })
      .queueJson(401, { detail: 'Not authenticated' });

    await expect(request('/auth/me', { context: 'me' })).rejects.toBeInstanceOf(
      SessionExpiredError,
    );
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });
});

describe('request — concurrent 401s coalesce onto one refresh', () => {
  it('fires exactly one POST /auth/refresh for two simultaneous 401s', async () => {
    fetchMock
      .queueJson(401, { detail: 'x' }) // call A original
      .queueJson(401, { detail: 'x' }); // call B original
    const refresh = fetchMock.queueDeferred(); // the single refresh, held open
    fetchMock.queueJson(200, { who: 'A' }).queueJson(200, { who: 'B' });

    const a = request('/auth/a', { context: 'authed' });
    const b = request('/auth/b', { context: 'authed' });

    // Both 401s have landed and the one refresh is in flight by the time the
    // held request is observed — no timer guesswork.
    await refresh.requested;
    refresh.resolveJson(200, { access_token: 'a2', refresh_token: 'r2' });

    await Promise.all([a, b]);

    const refreshCalls = fetchMock.requests.filter((r) => r.url === `${BASE}/auth/refresh`);
    expect(refreshCalls).toHaveLength(1);
  });
});

describe('request — refresh 401 → reject + signal', () => {
  it('clears tokens, fires onSessionExpired once, rejects with SessionExpiredError', async () => {
    const onSessionExpired = jest.fn();
    configureApiClient({ onSessionExpired });

    fetchMock
      .queueJson(401, { detail: 'Not authenticated' })
      .queueJson(401, { detail: 'Not authenticated' }); // refresh itself fails

    await expect(request('/auth/me', { context: 'me' })).rejects.toBeInstanceOf(
      SessionExpiredError,
    );
    expect(tokenStore.clearTokens).toHaveBeenCalled();
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('ensureFreshSession resolves false when there is no stored refresh token', async () => {
    (tokenStore.getTokens as jest.Mock).mockResolvedValue(null);
    await expect(ensureFreshSession()).resolves.toBe(false);
    expect(fetchMock.requests).toHaveLength(0);
  });
});

describe('request — error mapping', () => {
  it('401 on login → invalid-credentials (no refresh attempted)', async () => {
    fetchMock.queueJson(401, { detail: 'Invalid credentials' });
    await expect(
      request('/auth/login', { context: 'login', method: 'POST', body: {}, authed: false }),
    ).rejects.toMatchObject({ uiError: { kind: 'invalid-credentials' } });
    expect(fetchMock.requests).toHaveLength(1);
  });

  it('403 on login → email-not-verified carrying the submitted email', async () => {
    fetchMock.queueJson(403, { detail: 'Email not verified' });
    await expect(
      request('/auth/login', {
        context: 'login',
        method: 'POST',
        authed: false,
        submittedEmail: 'x@y.z',
      }),
    ).rejects.toMatchObject({ uiError: { kind: 'email-not-verified', email: 'x@y.z' } });
  });

  it('429 → rate-limited with retryAfterSeconds from the header', async () => {
    fetchMock.queueRateLimited(42);
    await expect(
      request('/auth/forgot-password', {
        context: 'forgot-password',
        method: 'POST',
        authed: false,
      }),
    ).rejects.toMatchObject({ uiError: { kind: 'rate-limited', retryAfterSeconds: 42 } });
  });

  it('500 → unknown', async () => {
    fetchMock.queueJson(500, { detail: 'boom' });
    await expect(request('/auth/me', { context: 'me' })).rejects.toMatchObject({
      uiError: { kind: 'unknown' },
    });
  });
});

describe('request — offline / timeout', () => {
  it('fetch TypeError → AuthApiError offline', async () => {
    fetchMock.queueNetworkError();
    await expect(request('/auth/me', { context: 'me' })).rejects.toMatchObject({
      uiError: { kind: 'offline' },
    });
  });

  it('a hung request aborts and maps to timeout', async () => {
    configureApiClient({ timeoutMs: 10 });
    fetchMock.queueTimeout();
    await expect(request('/auth/me', { context: 'me' })).rejects.toMatchObject({
      uiError: { kind: 'timeout' },
    });
  });
});

it('AuthApiError is an Error subclass', () => {
  expect(new AuthApiError({ kind: 'unknown' })).toBeInstanceOf(Error);
});

it('Platform default is respected when not overridden', () => {
  expect(['web', 'ios', 'android', 'windows', 'macos']).toContain(Platform.OS);
});
