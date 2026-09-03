/**
 * Global Jest setup (`setupFilesAfterEnv`).
 *
 * - `@testing-library/react-native` ≥ 12.4 registers its own Jest matchers on
 *   import, so there is no `@testing-library/jest-native/extend-expect` here —
 *   that package was dropped in T001 (deprecated, and it peer-conflicts with
 *   React 19).
 * - Routes `expo-secure-store` to an in-memory fake for every test.
 * - Resets the fake store and any `mockFetch()` global between tests so state
 *   never leaks across the suite.
 */
import { afterEach, jest } from '@jest/globals';

import '@testing-library/react-native';

import { resetSecureStoreMock } from './test-utils/expo-secure-store.mock';

jest.mock('expo-secure-store', () => require('./test-utils/expo-secure-store.mock'));

const originalFetch = globalThis.fetch;

afterEach(() => {
  resetSecureStoreMock();
  globalThis.fetch = originalFetch;
});
