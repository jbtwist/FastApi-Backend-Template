/**
 * Shared test helpers for the auth feature.
 *
 * Re-exports everything from `@testing-library/react-native` and adds:
 * - `renderWithProviders` / `renderHookWithProviders` — render a component or
 *   hook under the app-wide providers that don't need a navigation tree
 *   (safe-area). Screens that use `expo-router` (`<Link>`, `useRouter`,
 *   `<Redirect>`) should be rendered with `renderRouter` from
 *   `expo-router/testing-library` instead.
 * - `mockFetch` — a queueable `global.fetch` stand-in with `Retry-After`
 *   support, for exercising the `/auth` API contract without a server.
 * - the `expo-secure-store` fake helpers (`resetSecureStoreMock`,
 *   `secureStoreSnapshot`, `seedSecureStore`).
 */
import type { ReactElement, ReactNode } from 'react';
import { jest } from '@jest/globals';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  render,
  renderHook,
  type RenderHookOptions,
  type RenderHookResult,
  type RenderOptions,
  type RenderResult,
} from '@testing-library/react-native';

export * from '@testing-library/react-native';
export {
  resetSecureStoreMock,
  secureStoreSnapshot,
  seedSecureStore,
} from './expo-secure-store.mock';

// -- providers ---------------------------------------------------------------

/** Static safe-area metrics so `useSafeAreaInsets()` resolves synchronously in tests. */
const SAFE_AREA_METRICS = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

function Providers({ children }: { children: ReactNode }) {
  return <SafeAreaProvider initialMetrics={SAFE_AREA_METRICS}>{children}</SafeAreaProvider>;
}

export function renderWithProviders(
  ui: ReactElement,
  options: Omit<RenderOptions, 'wrapper'> = {},
): RenderResult {
  return render(ui, { wrapper: Providers, ...options });
}

export function renderHookWithProviders<Result, Props>(
  hook: (props: Props) => Result,
  options: Omit<RenderHookOptions<Props>, 'wrapper'> = {},
): RenderHookResult<Result, Props> {
  return renderHook(hook, { wrapper: Providers, ...options });
}

// -- fetch mock -------------------------------------------------------------

type QueuedResponse = {
  status?: number;
  /** Parsed by `res.json()`; serialized by `res.text()`. */
  body?: unknown;
  headers?: Record<string, string>;
  /** Reject with a `TypeError` (offline / DNS failure). */
  networkError?: boolean;
  /** Reject with an `AbortError` (request timed out). */
  timeout?: boolean;
};

type FetchImpl = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type MockFetch = jest.Mock<FetchImpl> & {
  /** Queue one response (FIFO). Chainable. */
  queueResponse: (res?: QueuedResponse) => MockFetch;
  /** Queue a JSON body with a status code (default 200). Chainable. */
  queueJson: (status: number, body?: unknown, headers?: Record<string, string>) => MockFetch;
  /** Queue a `429` carrying a `Retry-After` header (seconds). Chainable. */
  queueRateLimited: (retryAfterSeconds?: number) => MockFetch;
  /** Queue a rejected fetch (offline). Chainable. */
  queueNetworkError: () => MockFetch;
  /** Queue an `AbortError` (timeout). Chainable. */
  queueTimeout: () => MockFetch;
  /** Every request the mock received, as `{ url, init }`. */
  readonly requests: { url: string; init?: RequestInit }[];
  /** Restore whatever `global.fetch` was before this mock installed itself. */
  restore: () => void;
};

/**
 * Install a queueable `global.fetch`. Responses are consumed FIFO; a request
 * with an empty queue throws so a missing `queue*` call fails loudly.
 *
 * ```ts
 * const fetchMock = mockFetch();
 * fetchMock.queueJson(200, { access_token: 'a', refresh_token: 'r', token_type: 'bearer' });
 * fetchMock.queueRateLimited(30);
 * ```
 */
export function mockFetch(): MockFetch {
  const queue: QueuedResponse[] = [];
  const requests: { url: string; init?: RequestInit }[] = [];
  const previousFetch = globalThis.fetch;

  const fn = jest.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    requests.push({ url: typeof input === 'string' ? input : String(input), init });

    const next = queue.shift();
    if (!next) {
      throw new Error(
        `mockFetch: request with an empty queue (${init?.method ?? 'GET'} ${String(input)}) — ` +
          'add a queue* call for it',
      );
    }
    if (next.networkError) {
      throw new TypeError('Network request failed');
    }
    if (next.timeout) {
      const error = new Error('The operation was aborted');
      error.name = 'AbortError';
      throw error;
    }

    const status = next.status ?? 200;
    const headerEntries = Object.entries(next.headers ?? {}).map(
      ([key, value]) => [key.toLowerCase(), value] as const,
    );
    const headers = {
      get: (name: string) =>
        headerEntries.find(([key]) => key === name.toLowerCase())?.[1] ?? null,
      has: (name: string) => headerEntries.some(([key]) => key === name.toLowerCase()),
    };

    return {
      ok: status >= 200 && status < 300,
      status,
      headers,
      json: async () => (next.body === undefined ? {} : next.body),
      text: async () => (next.body === undefined ? '' : JSON.stringify(next.body)),
      clone() {
        return this;
      },
    } as unknown as Response;
  }) as MockFetch;

  fn.queueResponse = (res = {}) => {
    queue.push(res);
    return fn;
  };
  fn.queueJson = (status, body, headers) => {
    queue.push({ status, body, headers });
    return fn;
  };
  fn.queueRateLimited = (retryAfterSeconds = 30) => {
    queue.push({
      status: 429,
      body: { detail: 'Too Many Requests' },
      headers: { 'Retry-After': String(retryAfterSeconds) },
    });
    return fn;
  };
  fn.queueNetworkError = () => {
    queue.push({ networkError: true });
    return fn;
  };
  fn.queueTimeout = () => {
    queue.push({ timeout: true });
    return fn;
  };
  Object.defineProperty(fn, 'requests', { get: () => requests });
  fn.restore = () => {
    globalThis.fetch = previousFetch;
  };

  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}
