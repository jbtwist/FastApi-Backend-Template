import { DEFAULT_LOCALE, i18n } from '@/i18n';
import { en, es } from '@/i18n/locales';

import { email, minLength, required } from './validators';

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

  it('mentions the required length in the message', () => {
    expect(minLength(12)('short')).toContain('12');
  });
});

describe('messages', () => {
  afterEach(() => {
    i18n.locale = DEFAULT_LOCALE;
  });

  it('reads the catalogue at call time, so a locale switch applies', () => {
    const min12 = minLength(12);
    expect(required('')).toBe(en.validation.required);

    i18n.locale = 'es';
    expect(required('')).toBe(es.validation.required);
    expect(email('nope')).toBe(es.validation.email);
    expect(min12('short')).toContain('12');
  });
});
