/**
 * Global Jest setup (`setupFilesAfterEnv`).
 *
 * `@testing-library/react-native` ≥ 12.4 registers its matchers on import, so
 * no separate matcher-extension import is needed.
 */
import { afterEach, beforeEach, jest } from '@jest/globals';

import '@testing-library/react-native';

import { resetSecureStoreMock } from './test-utils/expo-secure-store.mock';

// Every test runs against the in-memory SecureStore fake.
jest.mock('expo-secure-store', () => require('./test-utils/expo-secure-store.mock'));

// AsyncStorage is a native module — without its official fake, importing
// anything that reaches `<LocaleProvider>` throws "NativeModule is null".
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// Snapshot `fetch` per test rather than once at load time: a `mockFetch()`
// installed in `beforeAll` is captured here and survives between tests, while a
// `mockFetch()` a test forgot to `.restore()` is rolled back after it.
let fetchAtTestStart: typeof globalThis.fetch;
beforeEach(() => {
  fetchAtTestStart = globalThis.fetch;
});
afterEach(() => {
  resetSecureStoreMock();
  globalThis.fetch = fetchAtTestStart;
});
