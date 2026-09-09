import AsyncStorage from '@react-native-async-storage/async-storage';
import type { TranslateOptions } from 'i18n-js';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { Platform } from 'react-native';

import { LOCALE_STORAGE_KEY, type Locale } from './config';
import { resolveInitialLocale } from './detect';
import { i18n } from './index';
import type { TranslationKey } from './types';

type LocaleContextValue = {
  locale: Locale;
  /** Persist an explicit choice and switch immediately. */
  setLocale: (next: Locale) => Promise<void>;
  /** Re-created per `locale` so a memoizing compiler can't cache a stale translation. */
  t: (key: TranslationKey, options?: TranslateOptions) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

async function readStoredLocale(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  // Renders at DEFAULT_LOCALE immediately (no async gate — a static/prerendered
  // export never runs the effect below) and switches reactively once the
  // stored/device locale resolves.
  const [locale, setLocaleState] = useState<Locale>(i18n.locale as Locale);

  useEffect(() => {
    let active = true;
    void readStoredLocale().then((stored) => {
      if (!active) return;
      const resolved = resolveInitialLocale(stored);
      i18n.locale = resolved;
      setLocaleState(resolved);
    });
    return () => {
      active = false;
    };
  }, []);

  // The prerendered HTML carries `lang="en"`; keep it truthful for screen
  // readers and translation prompts once the real locale is known.
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback(async (next: Locale) => {
    i18n.locale = next;
    setLocaleState(next);
    try {
      await AsyncStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // A failed write just means the choice isn't remembered next launch.
    }
  }, []);

  // Bound to `locale` so its identity changes on switch — a memoizing compiler
  // (React Compiler) caches a component's output by callback identity, and a
  // permanently-stable `t` would let stale-language renders survive setLocale().
  const boundT = useCallback(
    (key: TranslationKey, options?: TranslateOptions) => i18n.t(key, options),
    // `locale` isn't read in the body (i18n.t consults the mutable i18n.locale
    // field), but it must still gate this memo — that's the whole point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [locale],
  );

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t: boundT }),
    [locale, setLocale, boundT],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

function useLocaleContext(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useTranslation/useLocale must be used within <LocaleProvider>');
  return ctx;
}

/** `{ t, locale, setLocale }` — `t` output updates when the locale changes. */
export function useTranslation(): LocaleContextValue {
  return useLocaleContext();
}

/** `{ locale, setLocale }` — for a language switcher. */
export function useLocale(): Pick<LocaleContextValue, 'locale' | 'setLocale'> {
  const { locale, setLocale } = useLocaleContext();
  return { locale, setLocale };
}
