import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { LOCALE_STORAGE_KEY, type Locale } from './config';
import { resolveInitialLocale } from './detect';
import { i18n, t } from './index';

type LocaleContextValue = {
  locale: Locale;
  /** Persist an explicit choice and switch immediately. */
  setLocale: (next: Locale) => Promise<void>;
  t: typeof t;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

async function readStoredLocale(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(LOCALE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function LocaleProvider({
  children,
  fallback = null,
}: {
  children: ReactNode;
  /** Rendered until the stored/device locale is resolved (one async tick). */
  fallback?: ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(i18n.locale as Locale);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    void readStoredLocale().then((stored) => {
      if (!active) return;
      const resolved = resolveInitialLocale(stored);
      i18n.locale = resolved;
      setLocaleState(resolved);
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  const setLocale = useCallback(async (next: Locale) => {
    i18n.locale = next;
    setLocaleState(next);
    try {
      await AsyncStorage.setItem(LOCALE_STORAGE_KEY, next);
    } catch {
      // A failed write just means the choice isn't remembered next launch.
    }
  }, []);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t }),
    [locale, setLocale],
  );

  if (!ready) return <>{fallback}</>;
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
