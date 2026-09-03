import AsyncStorage from '@react-native-async-storage/async-storage';

import { PENDING_VERIFICATION_KEY, clear, get, set } from './pending-verification';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

beforeEach(() => AsyncStorage.clear());

it('returns null when nothing is stored', async () => {
  expect(await get()).toBeNull();
});

it('round-trips { email, lastSentAt }', async () => {
  await set({ email: 'user@example.com', lastSentAt: 1_700_000_000_000 });
  expect(await get()).toEqual({
    email: 'user@example.com',
    lastSentAt: 1_700_000_000_000,
  });
});

it('set overwrites the previous value', async () => {
  await set({ email: 'a@example.com', lastSentAt: 1 });
  await set({ email: 'b@example.com', lastSentAt: 2 });
  expect(await get()).toEqual({ email: 'b@example.com', lastSentAt: 2 });
});

it('clear removes the value', async () => {
  await set({ email: 'user@example.com', lastSentAt: 1 });
  await clear();
  expect(await get()).toBeNull();
});

it('returns null for corrupt JSON', async () => {
  await AsyncStorage.setItem(PENDING_VERIFICATION_KEY, '{not json');
  expect(await get()).toBeNull();
});

it('returns null when the stored shape is wrong', async () => {
  await AsyncStorage.setItem(PENDING_VERIFICATION_KEY, JSON.stringify({ email: 'x@y.co' }));
  expect(await get()).toBeNull();
});
