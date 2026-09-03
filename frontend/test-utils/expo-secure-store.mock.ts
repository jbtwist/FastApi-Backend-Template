/**
 * In-memory fake for `expo-secure-store`.
 *
 * Wired in for every test by `jest.mock('expo-secure-store', …)` in
 * `jest-setup.ts`. Implements the async key/value surface that
 * `src/auth/token-store.ts` (T021) depends on — `getItemAsync` /
 * `setItemAsync` / `deleteItemAsync` / `isAvailableAsync` — plus the
 * keychain-accessibility constants so `SecureStore` option objects still
 * resolve at call sites.
 */
import { jest } from '@jest/globals';

const store = new Map<string, string>();

export const getItemAsync = jest.fn(
  async (key: string): Promise<string | null> => (store.has(key) ? store.get(key)! : null),
);

export const setItemAsync = jest.fn(async (key: string, value: string): Promise<void> => {
  store.set(key, value);
});

export const deleteItemAsync = jest.fn(async (key: string): Promise<void> => {
  store.delete(key);
});

export const isAvailableAsync = jest.fn(async (): Promise<boolean> => true);

// Keychain-accessibility constants referenced inside SecureStore option objects.
export const AFTER_FIRST_UNLOCK = 'AFTER_FIRST_UNLOCK';
export const AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY = 'AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY';
export const ALWAYS = 'ALWAYS';
export const ALWAYS_THIS_DEVICE_ONLY = 'ALWAYS_THIS_DEVICE_ONLY';
export const WHEN_PASSCODE_SET_THIS_DEVICE_ONLY = 'WHEN_PASSCODE_SET_THIS_DEVICE_ONLY';
export const WHEN_UNLOCKED = 'WHEN_UNLOCKED';
export const WHEN_UNLOCKED_THIS_DEVICE_ONLY = 'WHEN_UNLOCKED_THIS_DEVICE_ONLY';

/** Wipe the fake store and reset call history. Called from `jest-setup.ts` after each test. */
export function resetSecureStoreMock(): void {
  store.clear();
  getItemAsync.mockClear();
  setItemAsync.mockClear();
  deleteItemAsync.mockClear();
  isAvailableAsync.mockClear();
}

/** Read the fake store directly — for assertions on what a test persisted. */
export function secureStoreSnapshot(): Record<string, string> {
  return Object.fromEntries(store);
}

/** Seed the fake store before a test (e.g. simulate an existing session). */
export function seedSecureStore(entries: Record<string, string>): void {
  for (const [key, value] of Object.entries(entries)) {
    store.set(key, value);
  }
}
