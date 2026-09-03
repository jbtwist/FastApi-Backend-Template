/**
 * In-memory fake for `expo-secure-store`, wired in suite-wide by `jest-setup.ts`.
 * Covers the async key/value surface plus the keychain-accessibility constants.
 */
import { jest } from '@jest/globals';

const store = new Map<string, string>();

const impl = {
  getItemAsync: async (key: string): Promise<string | null> =>
    store.has(key) ? store.get(key)! : null,
  setItemAsync: async (key: string, value: string): Promise<void> => {
    store.set(key, value);
  },
  deleteItemAsync: async (key: string): Promise<void> => {
    store.delete(key);
  },
  isAvailableAsync: async (): Promise<boolean> => true,
};

export const getItemAsync = jest.fn(impl.getItemAsync);
export const setItemAsync = jest.fn(impl.setItemAsync);
export const deleteItemAsync = jest.fn(impl.deleteItemAsync);
export const isAvailableAsync = jest.fn(impl.isAvailableAsync);

// Keychain-accessibility constants. The real module exposes these as numbers
// (native enum raw values), so a test that branches on one sees a number too.
export const AFTER_FIRST_UNLOCK = 0;
export const AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY = 1;
export const ALWAYS = 2;
export const WHEN_PASSCODE_SET_THIS_DEVICE_ONLY = 3;
export const ALWAYS_THIS_DEVICE_ONLY = 4;
export const WHEN_UNLOCKED = 5;
export const WHEN_UNLOCKED_THIS_DEVICE_ONLY = 6;

/**
 * Wipe the fake store and fully reset the mocks — `mockReset()`, not
 * `mockClear()`, so an unconsumed `mockResolvedValueOnce` / `mockRejectedValueOnce`
 * from one test can't leak into the next. The base implementation is reapplied.
 */
export function resetSecureStoreMock(): void {
  store.clear();
  getItemAsync.mockReset().mockImplementation(impl.getItemAsync);
  setItemAsync.mockReset().mockImplementation(impl.setItemAsync);
  deleteItemAsync.mockReset().mockImplementation(impl.deleteItemAsync);
  isAvailableAsync.mockReset().mockImplementation(impl.isAvailableAsync);
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
