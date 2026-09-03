/**
 * In-memory fake for `expo-secure-store`, wired in suite-wide by `jest-setup.ts`.
 * Covers the async key/value surface plus the keychain-accessibility constants.
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

// Keychain-accessibility constants, so SecureStore option objects still resolve at call sites.
export const AFTER_FIRST_UNLOCK = 'AFTER_FIRST_UNLOCK';
export const AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY = 'AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY';
export const ALWAYS = 'ALWAYS';
export const ALWAYS_THIS_DEVICE_ONLY = 'ALWAYS_THIS_DEVICE_ONLY';
export const WHEN_PASSCODE_SET_THIS_DEVICE_ONLY = 'WHEN_PASSCODE_SET_THIS_DEVICE_ONLY';
export const WHEN_UNLOCKED = 'WHEN_UNLOCKED';
export const WHEN_UNLOCKED_THIS_DEVICE_ONLY = 'WHEN_UNLOCKED_THIS_DEVICE_ONLY';

/** Wipe the fake store and reset call history. */
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
