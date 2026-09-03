/**
 * Shared test helpers.
 *
 * Re-exports `@testing-library/react-native` and adds:
 * - `renderWithProviders` / `renderHookWithProviders` — wrap in the providers
 *   that need no navigation tree (safe-area). Screens using `expo-router`
 *   (`<Link>`, `useRouter`, `<Redirect>`) need `renderRouter` from
 *   `expo-router/testing-library` instead.
 * - `mockFetch` — a queueable `global.fetch` stand-in.
 * - the `expo-secure-store` fake helpers.
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
  /**
   * A string is returned verbatim by `res.text()` and `JSON.parse`d by
   * `res.json()` (which throws on non-JSON, like a real `Response`). Anything
   * else is JSON-serialized for `text()` and returned as a deep copy by `json()`.
   */
  body?: unknown;
  headers?: Record<string, string>;
  /** Reject with a `TypeError` (offline / DNS failure). */
  networkError?: boolean;
  /** Never resolve; reject only when `init.signal` aborts (see `queueTimeout`). */
  timeout?: boolean;
};

/** A queue slot: either a ready response, or one `queueDeferred` holds open. */
type QueueEntry = QueuedResponse | { deferred: () => Promise<QueuedResponse> };

/** Handle for a request held open by `queueDeferred`. */
export type DeferredResponse = {
  /** Resolves once the mock has actually received the request this slot holds. */
  readonly requested: Promise<void>;
  /** Settle it with a full response spec (default: an empty `200`). */
  resolve: (res?: QueuedResponse) => void;
  /** Settle it with a JSON body and status (default `200`). */
  resolveJson: (status?: number, body?: unknown, headers?: Record<string, string>) => void;
  /** Fail it the way an offline fetch does. */
  rejectNetworkError: () => void;
};

type FetchImpl = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type MockFetch = jest.MockedFunction<FetchImpl> & {
  /** Queue one response (FIFO). Chainable. */
  queueResponse: (res?: QueuedResponse) => MockFetch;
  /** Queue a JSON body with a status code (default 200). Chainable. */
  queueJson: (status: number, body?: unknown, headers?: Record<string, string>) => MockFetch;
  /** Queue a `429` carrying a `Retry-After` header (seconds). Chainable. */
  queueRateLimited: (retryAfterSeconds?: number) => MockFetch;
  /** Queue a rejected fetch (offline). Chainable. */
  queueNetworkError: () => MockFetch;
  /**
   * Queue a request that hangs until its `AbortSignal` fires — the caller's
   * own timeout wiring has to abort it. With no `init.signal` it rejects with
   * an `AbortError` immediately so naive callers still get a failure. Chainable.
   */
  queueTimeout: () => MockFetch;
  /**
   * Queue a request that hangs until the returned handle settles it — the way
   * to hold one call open while others race past it (single-flight, coalescing,
   * in-flight deduplication). Returns the handle, so it does not chain.
   */
  queueDeferred: () => DeferredResponse;
  /** Every request the mock received, as `{ url, init }`. */
  readonly requests: { url: string; init?: RequestInit }[];
  /** Restore whatever `global.fetch` was before this mock installed itself. */
  restore: () => void;
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  if (typeof Request !== 'undefined' && input instanceof Request) return input.url;
  return String(input);
}

function abortError(): Error {
  const error = new Error('The operation was aborted');
  error.name = 'AbortError';
  return error;
}

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
  const queue: QueueEntry[] = [];
  const requests: { url: string; init?: RequestInit }[] = [];
  const previousFetch = globalThis.fetch;

  const fn = jest.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    requests.push({ url: requestUrl(input), init });

    const entry = queue.shift();
    if (!entry) {
      throw new Error(
        `mockFetch: request with an empty queue (${init?.method ?? 'GET'} ${requestUrl(input)}) — ` +
          'add a queue* call for it',
      );
    }
    // A deferred slot parks the request here until the test settles its handle.
    const next = 'deferred' in entry ? await entry.deferred() : entry;
    if (next.networkError) {
      throw new TypeError('Network request failed');
    }
    if (next.timeout) {
      const signal = init?.signal;
      if (!signal) throw abortError();
      if (signal.aborted) throw abortError();
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(abortError()), { once: true });
      });
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

    const bodyText =
      next.body === undefined
        ? ''
        : typeof next.body === 'string'
          ? next.body
          : JSON.stringify(next.body);
    const bodyJson = () => {
      if (next.body === undefined) return {};
      if (typeof next.body === 'string') return JSON.parse(next.body) as unknown;
      return structuredClone(next.body);
    };

    // A fresh `bodyUsed` per Response so `clone()` is genuinely independent and
    // a second read throws, like the platform `Response`.
    const build = (): Response => {
      let bodyUsed = false;
      const consume = () => {
        if (bodyUsed) throw new TypeError('Body is already consumed');
        bodyUsed = true;
      };
      return {
        ok: status >= 200 && status < 300,
        status,
        headers,
        get bodyUsed() {
          return bodyUsed;
        },
        json: async () => {
          consume();
          return bodyJson();
        },
        text: async () => {
          consume();
          return bodyText;
        },
        clone: () => build(),
      } as unknown as Response;
    };
    return build();
  }) as unknown as MockFetch;

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
  fn.queueDeferred = () => {
    let markRequested: () => void = () => {};
    const requested = new Promise<void>((resolve) => {
      markRequested = resolve;
    });
    let settle: (res: QueuedResponse) => void = () => {};
    const settled = new Promise<QueuedResponse>((resolve) => {
      settle = resolve;
    });

    queue.push({
      deferred: () => {
        markRequested();
        return settled;
      },
    });

    return {
      requested,
      resolve: (res = {}) => settle(res),
      resolveJson: (status = 200, body, headers) => settle({ status, body, headers }),
      rejectNetworkError: () => settle({ networkError: true }),
    };
  };
  Object.defineProperty(fn, 'requests', { get: () => requests });
  fn.restore = () => {
    globalThis.fetch = previousFetch;
  };

  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}
