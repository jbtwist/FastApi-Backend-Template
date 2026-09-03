/**
 * Global Jest setup (`setupFilesAfterEnv`).
 *
 * `@testing-library/react-native` ≥ 12.4 registers its matchers on import, so
 * no separate matcher-extension import is needed.
 */
import { afterEach, jest } from '@jest/globals';

import '@testing-library/react-native';

import { resetSecureStoreMock } from './test-utils/expo-secure-store.mock';

// Every test runs against the in-memory SecureStore fake.
jest.mock('expo-secure-store', () => require('./test-utils/expo-secure-store.mock'));

const originalFetch = globalThis.fetch;

// Undo a leftover `mockFetch()` and wipe fake-store state so nothing leaks between tests.
afterEach(() => {
  resetSecureStoreMock();
  globalThis.fetch = originalFetch;
});
