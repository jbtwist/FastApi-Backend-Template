import { Platform, Text } from 'react-native';

import { renderRouter, screen, act, waitFor } from 'expo-router/testing-library';

import { configureApiClient, resetApiClient } from '@/auth/api-client';
import { mockFetch, seedSecureStore, type MockFetch } from '@/test-utils';

jest.mock('@/components/animated-icon', () => ({ AnimatedSplashOverlay: () => null }));

const BASE = 'https://api.test';
const USER = { id: 'u1', email: 'a@b.c', email_verified: true };

const originalOS = Platform.OS;
function setPlatform(os: typeof Platform.OS) {
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
}

let fetchMock: MockFetch;

beforeEach(() => {
  setPlatform('ios');
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

/** A stored token pair + a `200 /me` → bootstrap lands on `signedIn`. */
function seedSignedIn() {
  seedSecureStore({ 'auth.accessToken': 'acc-1', 'auth.refreshToken': 'ref-1' });
  fetchMock.queueJson(200, USER);
}

const stub = (label: string) => {
  const Stub = () => <Text>{label}</Text>;
  Stub.displayName = `Stub(${label})`;
  return Stub;
};

/** The real layouts under test + stub leaves for every reachable route. */
function routes() {
  return {
    _layout: require('../_layout').default,
    '(auth)/_layout': require('../(auth)/_layout').default,
    '(auth)/sign-in': stub('sign-in screen'),
    '(app)/_layout': require('../(app)/_layout').default,
    '(app)/index': stub('app home'),
    'reset-password': stub('reset-password screen'),
    'verify-email-confirm': stub('verify-email-confirm screen'),
  };
}

describe('root splash gate', () => {
  it('withholds the navigator until bootstrap settles, then renders it', async () => {
    seedSecureStore({ 'auth.accessToken': 'acc-1', 'auth.refreshToken': 'ref-1' });
    const probe = fetchMock.queueDeferred();

    renderRouter(routes(), { initialUrl: '/' });

    // status === 'loading' — no route content on screen yet, but not a blank one.
    expect(screen.queryByText('app home')).toBeNull();
    expect(screen.getByLabelText('Loading')).toBeVisible();

    await act(async () => {
      probe.resolveJson(200, USER);
    });

    await waitFor(() => expect(screen.getByText('app home')).toBeVisible());
    expect(screen.queryByLabelText('Loading')).toBeNull();
  });
});

describe('(app) group — requires a session', () => {
  it('redirects a signed-out visitor to the sign-in screen', async () => {
    // no seed → no tokens → bootstrap resolves to signedOut, no /me call
    renderRouter(routes(), { initialUrl: '/' });

    await waitFor(() => expect(screen.getByText('sign-in screen')).toBeVisible());
    expect(screen.queryByText('app home')).toBeNull();
  });

  it('lets a signed-in visitor through to the authenticated area', async () => {
    seedSignedIn();
    renderRouter(routes(), { initialUrl: '/' });

    await waitFor(() => expect(screen.getByText('app home')).toBeVisible());
    expect(screen.queryByText('sign-in screen')).toBeNull();
  });
});

describe('(auth) group — bounces an active session', () => {
  it('redirects a signed-in visitor away from sign-in into the app', async () => {
    seedSignedIn();
    renderRouter(routes(), { initialUrl: '/sign-in' });

    await waitFor(() => expect(screen.getByText('app home')).toBeVisible());
    expect(screen.queryByText('sign-in screen')).toBeNull();
  });

  it('leaves a signed-out visitor on the sign-in screen', async () => {
    renderRouter(routes(), { initialUrl: '/sign-in' });

    await waitFor(() => expect(screen.getByText('sign-in screen')).toBeVisible());
  });
});

describe('top-level deep-link routes are never gated', () => {
  it('keeps a signed-out visitor on reset-password', async () => {
    renderRouter(routes(), { initialUrl: '/reset-password?token=abc' });

    await waitFor(() => expect(screen.getByText('reset-password screen')).toBeVisible());
    expect(screen.queryByText('sign-in screen')).toBeNull();
  });

  it('keeps a signed-in visitor on verify-email-confirm (no bounce into the app)', async () => {
    seedSignedIn();
    renderRouter(routes(), { initialUrl: '/verify-email-confirm?token=abc' });

    await waitFor(() =>
      expect(screen.getByText('verify-email-confirm screen')).toBeVisible(),
    );
    expect(screen.queryByText('app home')).toBeNull();
  });
});
