import {
  networkErrorToAuthUiError,
  parseRetryAfter,
  toAuthUiError,
} from '../errors';

describe('toAuthUiError — mapping table (contracts/auth-api.md)', () => {
  it('400 on confirm-email → invalid-token', () => {
    expect(
      toAuthUiError(400, 'Invalid or expired verification token', 'confirm-email'),
    ).toEqual({ kind: 'invalid-token' });
  });

  it('400 on reset-password → invalid-token', () => {
    expect(
      toAuthUiError(400, 'Invalid or expired reset token', 'reset-password'),
    ).toEqual({ kind: 'invalid-token' });
  });

  it('400 elsewhere → unknown', () => {
    expect(toAuthUiError(400, 'Bad request', 'login')).toEqual({ kind: 'unknown' });
  });

  it('401 on login → invalid-credentials', () => {
    expect(toAuthUiError(401, 'Invalid credentials', 'login')).toEqual({
      kind: 'invalid-credentials',
    });
  });

  it.each(['me', 'refresh', 'authed', 'logout'] as const)(
    '401 on %s → null (session logic, not a UI error)',
    (context) => {
      expect(toAuthUiError(401, 'Not authenticated', context)).toBeNull();
    },
  );

  it('403 on login → email-not-verified with the submitted email', () => {
    expect(
      toAuthUiError(403, 'Email not verified', 'login', {
        submittedEmail: 'user@example.com',
      }),
    ).toEqual({ kind: 'email-not-verified', email: 'user@example.com' });
  });

  it('403 on login without a submitted email → email is an empty string', () => {
    expect(toAuthUiError(403, 'Email not verified', 'login')).toEqual({
      kind: 'email-not-verified',
      email: '',
    });
  });

  it.each(['register', 'reset-password'] as const)(
    '422 on %s → password-policy carrying the server detail verbatim',
    (context) => {
      expect(
        toAuthUiError(422, 'Password is too short (minimum 12 characters)', context),
      ).toEqual({
        kind: 'password-policy',
        message: 'Password is too short (minimum 12 characters)',
      });
    },
  );

  it('422 with no detail → password-policy with a non-empty fallback message', () => {
    const result = toAuthUiError(422, undefined, 'register');
    expect(result).not.toBeNull();
    expect(result?.kind).toBe('password-policy');
    expect((result as { message: string }).message.length).toBeGreaterThan(0);
  });

  it('breached-password detail is identical whichever email was used (no divergence)', () => {
    const detail = 'This password has appeared in a data breach; choose another';
    expect(toAuthUiError(422, detail, 'register')).toEqual(
      toAuthUiError(422, detail, 'register'),
    );
  });

  it.each(['login', 'register', 'reset-password', 'forgot-password', 'resend-verification'] as const)(
    '429 on %s → rate-limited',
    (context) => {
      expect(toAuthUiError(429, 'Too many requests', context)).toEqual({
        kind: 'rate-limited',
      });
    },
  );

  it('429 carries retryAfterSeconds when provided', () => {
    expect(
      toAuthUiError(429, 'Too many requests', 'login', { retryAfterSeconds: 30 }),
    ).toEqual({ kind: 'rate-limited', retryAfterSeconds: 30 });
  });

  it.each([500, 502, 503, 418, 409])('%d → unknown', (status) => {
    expect(toAuthUiError(status, 'nope', 'login')).toEqual({ kind: 'unknown' });
  });
});

describe('networkErrorToAuthUiError', () => {
  it('AbortError → timeout', () => {
    const err = new Error('aborted');
    err.name = 'AbortError';
    expect(networkErrorToAuthUiError(err)).toEqual({ kind: 'timeout' });
  });

  it('TypeError (fetch could not reach the network) → offline', () => {
    expect(networkErrorToAuthUiError(new TypeError('Network request failed'))).toEqual({
      kind: 'offline',
    });
  });

  it('anything else → unknown', () => {
    expect(networkErrorToAuthUiError(new Error('weird'))).toEqual({ kind: 'unknown' });
    expect(networkErrorToAuthUiError('string')).toEqual({ kind: 'unknown' });
  });
});

describe('parseRetryAfter', () => {
  it('parses a delta-seconds value', () => {
    expect(parseRetryAfter('30')).toBe(30);
  });

  it('parses an HTTP-date value into whole seconds from now', () => {
    const tenSeconds = new Date(Date.now() + 10_000).toUTCString();
    const parsed = parseRetryAfter(tenSeconds);
    expect(parsed).toBeGreaterThanOrEqual(8);
    expect(parsed).toBeLessThanOrEqual(11);
  });

  it('returns undefined for null / empty / garbage', () => {
    expect(parseRetryAfter(null)).toBeUndefined();
    expect(parseRetryAfter('')).toBeUndefined();
    expect(parseRetryAfter('not-a-date')).toBeUndefined();
  });

  it('clamps a past HTTP-date to 0', () => {
    const past = new Date(Date.now() - 60_000).toUTCString();
    expect(parseRetryAfter(past)).toBe(0);
  });
});
