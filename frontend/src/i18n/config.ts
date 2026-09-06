/** Locale codes the app ships messages for. Add a code here and a `locales/<code>/` folder to grow. */
export const SUPPORTED_LOCALES = ['en', 'es'] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

/** Used before detection resolves and as the fallback for any gap in a translation. */
export const DEFAULT_LOCALE: Locale = 'en';

/** AsyncStorage key holding the user's explicit language choice (absent = follow the device). */
export const LOCALE_STORAGE_KEY = 'taskify.locale';

export function isSupportedLocale(value: string | null | undefined): value is Locale {
  return !!value && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}
