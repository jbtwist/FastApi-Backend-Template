import { request } from './api-client';
import * as authApi from './auth-api';

jest.mock('./api-client', () => ({
  request: jest.fn().mockResolvedValue(undefined),
}));

const mockRequest = request as jest.Mock;

beforeEach(() => mockRequest.mockClear());

describe('auth-api — each call delegates to request() with the contract shape', () => {
  it('register → POST /auth/register {email,password}, unauthenticated', async () => {
    await authApi.register({ email: 'a@b.c', password: 'pw' });
    expect(mockRequest).toHaveBeenCalledWith('/auth/register', {
      method: 'POST',
      body: { email: 'a@b.c', password: 'pw' },
      context: 'register',
      authed: false,
    });
  });

  it('login → POST /auth/login, carries submittedEmail for the 403 path', async () => {
    mockRequest.mockResolvedValueOnce({ id: 'u1', email: 'a@b.c', email_verified: true });
    const out = await authApi.login({ email: 'a@b.c', password: 'pw' });
    expect(mockRequest).toHaveBeenCalledWith('/auth/login', {
      method: 'POST',
      body: { email: 'a@b.c', password: 'pw' },
      context: 'login',
      authed: false,
      submittedEmail: 'a@b.c',
    });
    expect(out).toEqual({ id: 'u1', email: 'a@b.c', email_verified: true });
  });

  it('me → GET /auth/me, authenticated (default)', async () => {
    await authApi.me();
    expect(mockRequest).toHaveBeenCalledWith('/auth/me', { method: 'GET', context: 'me' });
  });

  it('refresh(token) → POST /auth/refresh { refresh_token } on native', async () => {
    await authApi.refresh('r-123');
    expect(mockRequest).toHaveBeenCalledWith('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: 'r-123' },
      context: 'refresh',
      authed: false,
    });
  });

  it('refresh() → POST /auth/refresh with no body on web', async () => {
    await authApi.refresh();
    expect(mockRequest).toHaveBeenCalledWith('/auth/refresh', {
      method: 'POST',
      body: undefined,
      context: 'refresh',
      authed: false,
    });
  });

  it('logout(token) → POST /auth/logout { refresh_token }', async () => {
    await authApi.logout('r-123');
    expect(mockRequest).toHaveBeenCalledWith('/auth/logout', {
      method: 'POST',
      body: { refresh_token: 'r-123' },
      context: 'logout',
      authed: false,
    });
  });

  it('logout() → POST /auth/logout with no body', async () => {
    await authApi.logout();
    expect(mockRequest).toHaveBeenCalledWith(
      '/auth/logout',
      expect.objectContaining({ method: 'POST', body: undefined, context: 'logout' }),
    );
  });

  it('confirmEmail → POST /auth/confirm-email { token }', async () => {
    await authApi.confirmEmail('tok');
    expect(mockRequest).toHaveBeenCalledWith('/auth/confirm-email', {
      method: 'POST',
      body: { token: 'tok' },
      context: 'confirm-email',
      authed: false,
    });
  });

  it('resendVerification → POST /auth/resend-verification { email }', async () => {
    await authApi.resendVerification('a@b.c');
    expect(mockRequest).toHaveBeenCalledWith('/auth/resend-verification', {
      method: 'POST',
      body: { email: 'a@b.c' },
      context: 'resend-verification',
      authed: false,
    });
  });

  it('forgotPassword → POST /auth/forgot-password { email }', async () => {
    await authApi.forgotPassword('a@b.c');
    expect(mockRequest).toHaveBeenCalledWith('/auth/forgot-password', {
      method: 'POST',
      body: { email: 'a@b.c' },
      context: 'forgot-password',
      authed: false,
    });
  });

  it('resetPassword → POST /auth/reset-password { token, new_password }', async () => {
    await authApi.resetPassword({ token: 'tok', new_password: 'newpw' });
    expect(mockRequest).toHaveBeenCalledWith('/auth/reset-password', {
      method: 'POST',
      body: { token: 'tok', new_password: 'newpw' },
      context: 'reset-password',
      authed: false,
    });
  });
});

it('authApi bundles all nine calls', () => {
  expect(Object.keys(authApi.authApi).sort()).toEqual(
    [
      'confirmEmail',
      'forgotPassword',
      'login',
      'logout',
      'me',
      'refresh',
      'register',
      'resendVerification',
      'resetPassword',
    ].sort(),
  );
});
