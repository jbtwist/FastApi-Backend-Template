/**
 * Public i18n surface for the app.
 *
 *   import { t } from '@/i18n';                       // one-off / non-component code
 *   import { useTranslation } from '@/i18n/provider'; // components that re-render on switch
 *
 * Messages live in `locales/<code>/*.json`, one file per namespace. Keys are
 * type-checked (`TranslationKey`) and `%{name}` placeholders are filled from the
 * options object. Pluralise with `{ count }`.
 */
import { I18n, type TranslateOptions } from 'i18n-js';

import { DEFAULT_LOCALE } from './config';
import { messages } from './locales';
import type { TranslationKey } from './types';

export const i18n = new I18n(messages, {
  defaultLocale: DEFAULT_LOCALE,
  locale: DEFAULT_LOCALE,
  // Any key `tsc` somehow lets through still renders in English rather than blank.
  enableFallback: true,
});

/** Look up a message by its typed key, filling `%{name}` placeholders from `options`. */
export function t(key: TranslationKey, options?: TranslateOptions): string {
  return i18n.t(key, options);
}

export { DEFAULT_LOCALE, LOCALE_LABELS, SUPPORTED_LOCALES, isSupportedLocale } from './config';
export type { Locale } from './config';
export type { TranslationKey } from './types';
