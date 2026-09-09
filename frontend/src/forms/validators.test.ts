import { DEFAULT_LOCALE, i18n, t } from '@/i18n';
import { en, es } from '@/i18n/locales';
import { resolveMessage } from '@/i18n/message';

import { email, maxLength, minLength, required } from './validators';

describe('required', () => {
  it('rejects empty and whitespace-only values', () => {
    expect(required('')).toBeDefined();
    expect(required('   ')).toBeDefined();
  });

  it('accepts any non-blank value', () => {
    expect(required('a')).toBeUndefined();
    expect(required('  hi  ')).toBeUndefined();
  });
});

describe('email', () => {
  it('accepts a plausible address (trimmed)', () => {
    expect(email('user@example.com')).toBeUndefined();
    expect(email('  user@example.com  ')).toBeUndefined();
    expect(email('a.b+tag@sub.example.co')).toBeUndefined();
  });

  it('rejects malformed addresses', () => {
    for (const bad of ['', 'user', 'user@', '@example.com', 'user@example', 'a b@example.com']) {
      expect(email(bad)).toBeDefined();
    }
  });
});

describe('minLength', () => {
  it('counts the raw string length, not trimmed', () => {
    const min12 = minLength(12);
    expect(min12('12345678901')).toBeDefined();
    expect(min12('123456789012')).toBeUndefined();
    expect(min12('            ')).toBeUndefined();
  });

  it('carries the required length as an option, not baked into text', () => {
    expect(minLength(12)('short')).toEqual({
      key: 'validation.minLength',
      options: { min: 12 },
    });
  });
});

describe('maxLength', () => {
  it('accepts the boundary and rejects one character past it', () => {
    const max128 = maxLength(128);
    expect(max128('a'.repeat(128))).toBeUndefined();
    expect(max128('a'.repeat(129))).toBeDefined();
  });

  it('carries the allowed length as an option, not baked into text', () => {
    expect(maxLength(128)('a'.repeat(129))).toEqual({
      key: 'validation.maxLength',
      options: { max: 128 },
    });
  });
});

describe('messages', () => {
  afterEach(() => {
    i18n.locale = DEFAULT_LOCALE;
  });

  it('returns keys, so the caller decides the language and can re-decide it', () => {
    expect(required('')).toBe('validation.required');
    expect(email('nope')).toBe('validation.email');
  });

  it('resolves through the catalogue in whichever locale is active', () => {
    expect(resolveMessage(t, required('')!)).toBe(en.validation.required);

    i18n.locale = 'es';
    expect(resolveMessage(t, required('')!)).toBe(es.validation.required);
    expect(resolveMessage(t, email('nope')!)).toBe(es.validation.email);
    expect(resolveMessage(t, minLength(12)('short')!)).toContain('12');
  });
});
