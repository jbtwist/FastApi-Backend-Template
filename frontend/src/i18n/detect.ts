import { getLocales } from 'expo-localization';

import { DEFAULT_LOCALE, isSupportedLocale, type Locale } from './config';

/**
 * The first device-preferred language we ship messages for, else `DEFAULT_LOCALE`.
 * `getLocales()` is ordered by the user's preference list, so the first supported
 * match wins.
 */
export function deviceLocale(): Locale {
  for (const { languageCode } of getLocales()) {
    if (isSupportedLocale(languageCode)) return languageCode;
  }
  return DEFAULT_LOCALE;
}

/** `'ltr' | 'rtl'` for the device's primary language — for a future RTL locale. */
export function deviceTextDirection(): 'ltr' | 'rtl' {
  return getLocales()[0]?.textDirection ?? 'ltr';
}

/** Stored explicit choice wins; otherwise follow the device. */
export function resolveInitialLocale(stored: string | null | undefined): Locale {
  return isSupportedLocale(stored) ? stored : deviceLocale();
}
