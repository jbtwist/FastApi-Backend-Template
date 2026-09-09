/**
 * The transport layer for every `/auth` call.
 *
 * Responsibilities (contracts/auth-api.md — "Transport per platform" +
 * "Refresh-on-401 protocol"):
 *  - attach the session: `Authorization: Bearer` on native, `credentials: 'include'`
 *    on web
 *  - map any failure to a typed `AuthUiError` via `errors.ts`
 *  - on a `401` for an authenticated call, run a **single-flight** refresh and
 *    retry the original request exactly once; if the refresh fails, clear the
 *    local session and notify the provider.
 */
import { Platform } from 'react-native';

import { authConfig } from './config';
import {
  type AuthEndpointContext,
  type AuthUiError,
  networkErrorToAuthUiError,
  parseRetryAfter,
  toAuthUiError,
} from './errors';
import { clearTokens, getTokens, setTokens } from './token-store';

export type ClientPlatform = 'web' | 'native';

/** Thrown for every failed call. `uiError` is what the screens render. */
export class AuthApiError extends Error {
  constructor(
    readonly uiError: AuthUiError,
    readonly status?: number,
  ) {
    super(`AuthApiError(${uiError.kind}${status ? ` ${status}` : ''})`);
    this.name = 'AuthApiError';
  }
}

/**
 * Thrown when an authenticated call could not be recovered — the refresh
 * failed (or a second `401` came back after a successful refresh). The local
 * session has already been cleared and `onSessionExpired` fired; `auth-context`
 * catches this to move to `expired → signedOut`.
 */
export class SessionExpiredError extends Error {
  constructor() {
    super('SessionExpiredError');
    this.name = 'SessionExpiredError';
  }
}

export interface ApiClientConfig {
  baseUrl: string;
  platform: ClientPlatform;
  /** Fired once when an authenticated call ends in an unrecoverable `401`. */
  onSessionExpired?: () => void;
  /** Per-request timeout; a hung request rejects as `{ kind: 'timeout' }`. */
  timeoutMs: number;
}

const defaultConfig: ApiClientConfig = {
  baseUrl: authConfig.apiBaseUrl,
  platform: Platform.OS === 'web' ? 'web' : 'native',
  timeoutMs: 15_000,
};

let config: ApiClientConfig = { ...defaultConfig };

/** Override client config (DI for tests, wiring from `auth-context`). */
export function configureApiClient(patch: Partial<ApiClientConfig>): void {
  config = { ...config, ...patch };
}

/** Reset to defaults — used between tests. */
export function resetApiClient(): void {
  config = { ...defaultConfig };
  refreshInFlight = null;
}

export interface RequestOptions {
  method?: 'GET' | 'POST';
  /** JSON-serialisable request body. */
  body?: unknown;
  /** Endpoint context — drives error mapping and the refresh decision. */
  context: AuthEndpointContext;
  /**
   * Whether this call carries the session and should trigger refresh-on-401.
  authed?: boolean;
  /** Email typed into the form. */
  submittedEmail?: string;
  /** Caller-supplied abort signal, combined with the internal timeout. */
  signal?: AbortSignal;
}

const PUBLIC_CONTEXTS: ReadonlySet<AuthEndpointContext> = new Set([
  'login',
  'register',
  'forgot-password',
  'confirm-email',
  'reset-password',
  'resend-verification',
  'refresh',
  'logout',
]);

function isAuthed(options: RequestOptions): boolean {
  return options.authed ?? !PUBLIC_CONTEXTS.has(options.context);
}

interface RawResponse {
  ok: boolean;
  status: number;
  retryAfterSeconds?: number;
  detail: unknown;
  json: unknown;
}

async function rawFetch(
  path: string,
  options: RequestOptions,
  withAuth: boolean,
): Promise<RawResponse> {
  const url = `${config.baseUrl}${path}`;
  const headers: Record<string, string> = { Accept: 'application/json' };
  const init: RequestInit = { method: options.method ?? 'GET', headers };

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }

  if (config.platform === 'web') {
    init.credentials = 'include';
  } else if (withAuth) {
    const tokens = await getTokens();
    if (tokens) headers.Authorization = `Bearer ${tokens.accessToken}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.timeoutMs);
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener('abort', () => controller.abort(), { once: true });
  }
  init.signal = controller.signal;

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    throw new AuthApiError(networkErrorToAuthUiError(error));
  } finally {
    clearTimeout(timer);
  }

  let json: unknown;
  try {
    const text = await response.text();
    json = text ? JSON.parse(text) : undefined;
  } catch {
    json = undefined;
  }

  const detail =
    json && typeof json === 'object' ? (json as { detail?: unknown }).detail : undefined;

  return {
    ok: response.ok,
    status: response.status,
    retryAfterSeconds: parseRetryAfter(response.headers.get('Retry-After')),
    detail,
    json,
  };
}

let refreshInFlight: Promise<boolean> | null = null;

/**
 * Run a refresh, coalescing concurrent callers onto one in-flight `POST
 * /auth/refresh`. Resolves `true` when a fresh session is in place, `false`
 * when the refresh failed (local tokens are then cleared on native).
 */
export function ensureFreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function doRefresh(): Promise<boolean> {
  let body: string | undefined;
  const headers: Record<string, string> = { Accept: 'application/json' };
  const init: RequestInit = { method: 'POST', headers };

  if (config.platform === 'web') {
    init.credentials = 'include';
  } else {
    const tokens = await getTokens();
    if (!tokens) return false;
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify({ refresh_token: tokens.refreshToken });
  }
  init.body = body;

  let response: Response;
  try {
    response = await fetch(`${config.baseUrl}/auth/refresh`, init);
  } catch {
    return false;
  }

  if (!response.ok) {
    if (config.platform !== 'web') await clearTokens().catch(() => undefined);
    return false;
  }

  if (config.platform !== 'web') {
    try {
      const pair = (await response.json()) as {
        access_token?: string;
        refresh_token?: string;
      };
      if (!pair.access_token || !pair.refresh_token) return false;
      await setTokens({ accessToken: pair.access_token, refreshToken: pair.refresh_token });
    } catch {
      return false;
    }
  }
  return true;
}

function mapError(raw: RawResponse, options: RequestOptions): AuthApiError {
  const uiError =
    toAuthUiError(raw.status, raw.detail, options.context, {
      submittedEmail: options.submittedEmail,
      retryAfterSeconds: raw.retryAfterSeconds,
    }) ?? { kind: 'unknown' };
  return new AuthApiError(uiError, raw.status);
}

/**
 * Perform one `/auth` request. Returns the parsed JSON body (or `undefined`
 * for a `204`). Throws `AuthApiError` for a mapped failure, or
 * `SessionExpiredError` when an authed call could not be recovered.
 */
export async function request<T = unknown>(path: string, options: RequestOptions): Promise<T> {
  const authed = isAuthed(options);
  let raw = await rawFetch(path, options, authed);

  if (raw.ok) return raw.json as T;

  if (raw.status === 401 && authed) {
    const refreshed = await ensureFreshSession();
    if (!refreshed) {
      config.onSessionExpired?.();
      throw new SessionExpiredError();
    }

    raw = await rawFetch(path, options, true);
    if (raw.ok) return raw.json as T;

    if (raw.status === 401) {
      config.onSessionExpired?.();
      throw new SessionExpiredError();
    }
  }

  throw mapError(raw, options);
}
