import AsyncStorage from '@react-native-async-storage/async-storage';

import { PENDING_VERIFICATION_KEY, clear, get, isSameEmail, set } from './pending-verification';

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

describe('when device storage is unavailable (e.g. blocked site data)', () => {
  it('set resolves instead of failing the registration that called it', async () => {
    jest.spyOn(AsyncStorage, 'setItem').mockRejectedValueOnce(new Error('QuotaExceededError'));
    await expect(set({ email: 'user@example.com', lastSentAt: 1 })).resolves.toBeUndefined();
  });

  it('clear resolves too', async () => {
    jest.spyOn(AsyncStorage, 'removeItem').mockRejectedValueOnce(new Error('SecurityError'));
    await expect(clear()).resolves.toBeUndefined();
  });
});

describe('isSameEmail', () => {
  it('ignores case and surrounding whitespace, as the backend does', () => {
    expect(isSameEmail(' Alice@Example.com ', 'alice@example.com')).toBe(true);
  });

  it('tells different addresses apart', () => {
    expect(isSameEmail('alice@example.com', 'bob@example.com')).toBe(false);
  });
});
