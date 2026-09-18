/**
 * One typed function per `/auth` endpoint the frontend calls, each a thin
 * delegate to `api-client`'s `request()`. The API's own OpenAPI spec, at `/docs`
 * on the running backend, is the source of truth for method, path, body and
 * status.
 *
 * Error handling, transport and refresh-on-401 all live in `api-client`; this
 * module only names the calls and types their payloads.
 */
import type { OAuthProvider } from './config';
import { request } from './api-client';

/** `UserOut` from the API. */
export interface UserOut {
  id: string;
  email: string;
  email_verified: boolean;
}

/** `TokenPairOut` from the API (snake_case wire shape). */
export interface TokenPairOut {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
}

/** `LoginOut` — identity plus the token pair, returned by `POST /auth/login`. */
export type LoginOut = UserOut & TokenPairOut;

/** `POST /auth/register` → `204`, identical whether or not the email is taken. */
export function register(body: { email: string; password: string }): Promise<void> {
  return request<void>('/auth/register', {
    method: 'POST',
    body,
    context: 'register',
    authed: false,
  });
}

/** `POST /auth/login` → `200 LoginOut` (+ Set-Cookie on web). */
export function login(body: { email: string; password: string }): Promise<LoginOut> {
  return request<LoginOut>('/auth/login', {
    method: 'POST',
    body,
    context: 'login',
    authed: false,
    submittedEmail: body.email,
  });
}

/** `GET /auth/me` → `200 UserOut`. Authenticated; a `401` drives refresh / sign-out. */
export function me(): Promise<UserOut> {
  return request<UserOut>('/auth/me', { method: 'GET', context: 'me' });
}

/**
 * `POST /auth/refresh` → `200 TokenPairOut`.
 * Native passes its stored `refreshToken`; web passes nothing (the refresh
 * cookie, scoped `path=/auth`, is sent automatically).
 *
 * Prefer `api-client`'s `ensureFreshSession()` for the transparent
 * refresh-on-401 path — this typed call is for explicit refreshes.
 */
export function refresh(refreshToken?: string): Promise<TokenPairOut> {
  return request<TokenPairOut>('/auth/refresh', {
    method: 'POST',
    body: refreshToken ? { refresh_token: refreshToken } : undefined,
    context: 'refresh',
    authed: false,
  });
}

/** `POST /auth/logout` → `204` (idempotent). Best-effort; callers clear local state regardless. */
export function logout(refreshToken?: string): Promise<void> {
  return request<void>('/auth/logout', {
    method: 'POST',
    body: refreshToken ? { refresh_token: refreshToken } : undefined,
    context: 'logout',
    authed: false,
  });
}

/** `POST /auth/confirm-email` `{ token }` → `204` | `400`. */
export function confirmEmail(token: string): Promise<void> {
  return request<void>('/auth/confirm-email', {
    method: 'POST',
    body: { token },
    context: 'confirm-email',
    authed: false,
  });
}

/** `POST /auth/resend-verification` `{ email }` → `204` always (no enumeration). */
export function resendVerification(email: string): Promise<void> {
  return request<void>('/auth/resend-verification', {
    method: 'POST',
    body: { email },
    context: 'resend-verification',
    authed: false,
  });
}

/** `POST /auth/forgot-password` `{ email }` → `204` always (~500 ms floor). */
export function forgotPassword(email: string): Promise<void> {
  return request<void>('/auth/forgot-password', {
    method: 'POST',
    body: { email },
    context: 'forgot-password',
    authed: false,
  });
}

/** `POST /auth/reset-password` `{ token, new_password }` → `204` (revokes all sessions) | `400` | `422`. */
export function resetPassword(body: { token: string; new_password: string }): Promise<void> {
  return request<void>('/auth/reset-password', {
    method: 'POST',
    body,
    context: 'reset-password',
    authed: false,
  });
}

/** `OAuthProvidersOut` — which providers this deployment offers. */
export interface OAuthProvidersOut {
  providers: OAuthProvider[];
}

/** `OAuthStartOut` — the `state` + `nonce` a native sign-in attempt runs on. */
export interface OAuthStartOut {
  state: string;
  nonce: string;
  expires_in: number;
}

/** `GET /auth/oauth/providers` → `200 OAuthProvidersOut`. Never an error. */
export function oauthProviders(): Promise<OAuthProvidersOut> {
  return request<OAuthProvidersOut>('/auth/oauth/providers', {
    method: 'GET',
    context: 'oauth',
    authed: false,
  });
}

/** `POST /auth/oauth/{provider}/start` → `200 OAuthStartOut`. `404` if unknown/unconfigured. */
export function oauthStart(
  provider: OAuthProvider,
  redirectTarget?: string,
): Promise<OAuthStartOut> {
  return request<OAuthStartOut>(`/auth/oauth/${provider}/start`, {
    method: 'POST',
    body: redirectTarget ? { redirect_target: redirectTarget } : undefined,
    context: 'oauth',
    authed: false,
  });
}

/**
 * `POST /auth/oauth/{provider}/native` → `200 LoginOut` (same body as
 * `POST /auth/login`) | `401` | `403` | `503`.
 */
export function oauthNative(
  provider: OAuthProvider,
  body: { state: string; assertion: string; display_name?: string },
): Promise<LoginOut> {
  return request<LoginOut>(`/auth/oauth/${provider}/native`, {
    method: 'POST',
    body,
    context: 'oauth',
    authed: false,
  });
}

export const authApi = {
  register,
  login,
  me,
  refresh,
  logout,
  confirmEmail,
  resendVerification,
  forgotPassword,
  resetPassword,
  oauthProviders,
  oauthStart,
  oauthNative,
};
