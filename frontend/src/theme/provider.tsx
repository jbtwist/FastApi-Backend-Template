/**
 * Holds the active colour scheme: the user's stored choice when there is one,
 * the device's setting otherwise.
 *
 * The stored preference is only ever `light` or `dark`. "Follow the device" is
 * the absence of a preference rather than a third value, so it needs no entry in
 * the switcher and no migration if the device setting changes underfoot — until
 * someone picks a side, `useActiveColorScheme` simply reports whatever the OS
 * currently says.
 */
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

import { useColorScheme as useDeviceColorScheme } from '@/hooks/use-color-scheme';

import { COLOR_SCHEME_STORAGE_KEY, isColorScheme, type ColorScheme } from './config';

type ColorSchemeContextValue = {
  /** What is on screen right now — the preference, or the device's setting. */
  scheme: ColorScheme;
  /** The stored choice. `null` means none has been made, so the device wins. */
  preference: ColorScheme | null;
  /** Persist an explicit choice and switch immediately. */
  setScheme: (next: ColorScheme) => Promise<void>;
};

const ColorSchemeContext = createContext<ColorSchemeContextValue | null>(null);

/** Anything the platform reports that isn't `dark` renders as light. */
function normalize(value: string | null | undefined): ColorScheme {
  return value === 'dark' ? 'dark' : 'light';
}

async function readStoredScheme(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(COLOR_SCHEME_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function ColorSchemeProvider({ children }: { children: ReactNode }) {
  const device = useDeviceColorScheme();
  const [preference, setPreference] = useState<ColorScheme | null>(null);

  useEffect(() => {
    let active = true;
    void readStoredScheme().then((stored) => {
      if (active && isColorScheme(stored)) setPreference(stored);
    });
    return () => {
      active = false;
    };
  }, []);

  const setScheme = useCallback(async (next: ColorScheme) => {
    setPreference(next);
    try {
      await AsyncStorage.setItem(COLOR_SCHEME_STORAGE_KEY, next);
    } catch {
      // A failed write just means the choice isn't remembered next launch.
    }
  }, []);

  const scheme = preference ?? normalize(device);

  const value = useMemo<ColorSchemeContextValue>(
    () => ({ scheme, preference, setScheme }),
    [scheme, preference, setScheme],
  );

  return <ColorSchemeContext.Provider value={value}>{children}</ColorSchemeContext.Provider>;
}

/**
 * The scheme to paint with.
 *
 * Falls back to the device's setting outside a provider rather than throwing:
 * every themed component calls this through `useTheme`, and a missing provider
 * should cost the override, not the colours.
 */
export function useActiveColorScheme(): ColorScheme {
  const ctx = useContext(ColorSchemeContext);
  const device = useDeviceColorScheme();
  return ctx?.scheme ?? normalize(device);
}

/**
 * `{ scheme, preference, setScheme }` — for a theme switcher.
 *
 * Throws outside a provider: a switcher with nothing to write to would render
 * as a control that silently does nothing.
 */
export function useColorSchemeChoice(): ColorSchemeContextValue {
  const ctx = useContext(ColorSchemeContext);
  if (!ctx) throw new Error('useColorSchemeChoice must be used within <ColorSchemeProvider>');
  return ctx;
}
