/**
 * Global Jest setup (`setupFilesAfterEnv`).
 *
 * `@testing-library/react-native` ≥ 12.4 registers its matchers on import, so
 * no separate matcher-extension import is needed.
 */
import { afterEach, beforeEach, jest } from '@jest/globals';

import '@testing-library/react-native';

import { resetSecureStoreMock } from './src/test-utils/expo-secure-store.mock';

// A fake Google client ID on every platform, so `authConfig.googleClientIds`
// is populated the same way in every test run. Real values only ever matter
// against a real Google project; the platform SDK itself is always faked at
// the module edge in tests (`frontend-contract.md`).
process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_WEB ??= 'test-google-client-id-web';
process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_IOS ??= 'test-google-client-id-ios';
process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_ANDROID ??= 'test-google-client-id-android';

// Every test runs against the in-memory SecureStore fake.
jest.mock('expo-secure-store', () => require('./src/test-utils/expo-secure-store.mock'));

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
