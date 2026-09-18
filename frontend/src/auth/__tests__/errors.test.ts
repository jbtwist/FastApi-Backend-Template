import {
  networkErrorToAuthUiError,
  oauthErrorCodeToAuthUiError,
  parseRetryAfter,
  toAuthUiError,
} from '../errors';

describe('toAuthUiError — mapping table', () => {
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
    '422 on %s → password-policy, dropping the server detail',
    (context) => {
      expect(
        toAuthUiError(422, 'Password is too short (minimum 12 characters)', context),
      ).toEqual({ kind: 'password-policy' });
    },
  );

  it('422 with no detail → password-policy all the same', () => {
    expect(toAuthUiError(422, undefined, 'register')).toEqual({ kind: 'password-policy' });
  });

  it('carries no server copy, whatever detail the backend sent', () => {
    // Screens render their own translated message, so two different server
    // wordings must be indistinguishable here.
    expect(toAuthUiError(422, 'This password has appeared in a data breach', 'register')).toEqual(
      toAuthUiError(422, 'Password exceeds the maximum length of 128 characters', 'register'),
    );
  });

  it.each(['register', 'login', 'forgot-password', 'resend-verification'] as const)(
    '422 on %s with a rejected email field → invalid-email, not a password message',
    (context) => {
      const detail = [
        {
          type: 'value_error',
          loc: ['body', 'email'],
          msg: 'value is not a valid email address',
        },
      ];
      expect(toAuthUiError(422, detail, context)).toEqual({ kind: 'invalid-email' });
    },
  );

  it('422 naming another field → unknown (nothing useful to show)', () => {
    const detail = [{ type: 'missing', loc: ['body', 'token'], msg: 'Field required' }];
    expect(toAuthUiError(422, detail, 'reset-password')).toEqual({ kind: 'unknown' });
  });

  it('breached-password detail is identical whichever email was used (no divergence)', () => {
    const detail = 'This password has appeared in a data breach; choose another';
    expect(toAuthUiError(422, detail, 'register')).toEqual(toAuthUiError(422, detail, 'register'));
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

describe('toAuthUiError — oauth context', () => {
  it('401 on oauth → oauth-failed (assertion rejected, no session-refresh logic)', () => {
    expect(toAuthUiError(401, 'Invalid assertion', 'oauth')).toEqual({ kind: 'oauth-failed' });
  });

  it('403 on oauth → oauth-email-unverified, never login\'s email-not-verified', () => {
    const oauthResult = toAuthUiError(403, { detail: 'email_not_verified_by_provider' }, 'oauth');

    expect(oauthResult).toEqual({ kind: 'oauth-email-unverified' });
    expect(oauthResult).not.toEqual(
      toAuthUiError(403, 'Email not verified', 'login', { submittedEmail: 'user@example.com' }),
    );
  });

  it('404 on oauth → oauth-not-enabled (unknown or unconfigured provider)', () => {
    expect(toAuthUiError(404, undefined, 'oauth')).toEqual({ kind: 'oauth-not-enabled' });
  });

  it('503 on oauth → oauth-unavailable', () => {
    expect(toAuthUiError(503, undefined, 'oauth')).toEqual({ kind: 'oauth-unavailable' });
  });

  it('503 elsewhere is still unknown — the oauth mapping does not leak to other contexts', () => {
    expect(toAuthUiError(503, undefined, 'login')).toEqual({ kind: 'unknown' });
  });
});

describe('toAuthUiError — an email already linked to another provider', () => {
  it('409 on oauth → oauth-email-linked-elsewhere, naming the provider the body carries', () => {
    expect(
      toAuthUiError(409, 'Email linked to another provider', 'oauth', { linkedProvider: 'apple' }),
    ).toEqual({ kind: 'oauth-email-linked-elsewhere', linkedProvider: 'apple' });
  });

  it('a provider name the app does not know is dropped, not rendered', () => {
    expect(toAuthUiError(409, undefined, 'oauth', { linkedProvider: '<b>evil</b>' })).toEqual({
      kind: 'oauth-email-linked-elsewhere',
    });
  });

  it('409 on oauth-link-confirm maps the same way', () => {
    expect(toAuthUiError(409, undefined, 'oauth-link-confirm', { linkedProvider: 'google' })).toEqual(
      { kind: 'oauth-email-linked-elsewhere', linkedProvider: 'google' },
    );
  });

  it('400 on oauth-link-confirm → invalid-token', () => {
    expect(toAuthUiError(400, undefined, 'oauth-link-confirm')).toEqual({ kind: 'invalid-token' });
  });
});

describe('oauthErrorCodeToAuthUiError — the web return leg\'s oauth_error flag', () => {
  it('cancelled → oauth-cancelled', () => {
    expect(oauthErrorCodeToAuthUiError('cancelled')).toEqual({ kind: 'oauth-cancelled' });
  });

  it('failed → oauth-failed', () => {
    expect(oauthErrorCodeToAuthUiError('failed')).toEqual({ kind: 'oauth-failed' });
  });

  it('unavailable → oauth-unavailable', () => {
    expect(oauthErrorCodeToAuthUiError('unavailable')).toEqual({ kind: 'oauth-unavailable' });
  });

  it('email_not_verified_by_provider → oauth-email-unverified', () => {
    expect(oauthErrorCodeToAuthUiError('email_not_verified_by_provider')).toEqual({
      kind: 'oauth-email-unverified',
    });
  });

  it('email_linked_to_other_provider → oauth-email-linked-elsewhere with the flagged provider', () => {
    expect(oauthErrorCodeToAuthUiError('email_linked_to_other_provider', 'google')).toEqual({
      kind: 'oauth-email-linked-elsewhere',
      linkedProvider: 'google',
    });
  });

  it('email_linked_to_other_provider with an unknown provider flag → no provider named', () => {
    expect(oauthErrorCodeToAuthUiError('email_linked_to_other_provider', 'myspace')).toEqual({
      kind: 'oauth-email-linked-elsewhere',
    });
  });

  it('an unrecognised code → unknown', () => {
    expect(oauthErrorCodeToAuthUiError('made-up')).toEqual({ kind: 'unknown' });
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
