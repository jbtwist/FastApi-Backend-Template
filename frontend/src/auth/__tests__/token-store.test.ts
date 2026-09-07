import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

import { clearTokens, getTokens, setTokens } from '../token-store';

jest.mock('expo-secure-store', () => {
  const store = new Map<string, string>();
  return {
    __store: store,
    getItemAsync: jest.fn(async (key: string) =>
      store.has(key) ? store.get(key)! : null,
    ),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      store.set(key, value);
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      store.delete(key);
    }),
  };
});

const mockStore = (SecureStore as unknown as { __store: Map<string, string> }).__store;
const originalOS = Platform.OS;

function setPlatform(os: typeof Platform.OS) {
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });
}

beforeEach(() => {
  mockStore.clear();
  jest.clearAllMocks();
});

afterEach(() => {
  setPlatform(originalOS);
});

const PAIR = { accessToken: 'access-abc', refreshToken: 'refresh-xyz' };

describe('token-store on native', () => {
  beforeEach(() => setPlatform('ios'));

  it('round-trips a token pair through secure storage', async () => {
    await setTokens(PAIR);
    await expect(getTokens()).resolves.toEqual(PAIR);
    expect(SecureStore.setItemAsync).toHaveBeenCalled();
  });

  it('returns null when nothing is stored', async () => {
    await expect(getTokens()).resolves.toBeNull();
  });

  it('clearTokens removes the pair', async () => {
    await setTokens(PAIR);
    await clearTokens();
    await expect(getTokens()).resolves.toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalled();
  });

  it('treats a partial pair (only one token present) as null and clears the stray value', async () => {
    await setTokens(PAIR);
    // simulate one key going missing
    for (const key of [...mockStore.keys()]) {
      if (mockStore.get(key) === PAIR.refreshToken) mockStore.delete(key);
    }
    await expect(getTokens()).resolves.toBeNull();
    // stray access token cleared on the failed read
    await expect(getTokens()).resolves.toBeNull();
    expect(mockStore.size).toBe(0);
  });

  it('treats an empty stored value as null and clears the store', async () => {
    await setTokens(PAIR);
    for (const key of [...mockStore.keys()]) mockStore.set(key, '');
    await expect(getTokens()).resolves.toBeNull();
    expect(mockStore.size).toBe(0);
  });

  it('returns null (does not throw) when secure storage read fails', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error('keychain locked'));
    await expect(getTokens()).resolves.toBeNull();
  });

  it('rejects a malformed pair passed to setTokens', async () => {
    await expect(
      setTokens({ accessToken: '', refreshToken: 'x' } as never),
    ).rejects.toBeInstanceOf(Error);
  });
});

describe('token-store on web (no-op)', () => {
  beforeEach(() => setPlatform('web'));

  it('getTokens is always null and touches no storage', async () => {
    await expect(getTokens()).resolves.toBeNull();
    expect(SecureStore.getItemAsync).not.toHaveBeenCalled();
  });

  it('setTokens is a no-op', async () => {
    await setTokens(PAIR);
    expect(SecureStore.setItemAsync).not.toHaveBeenCalled();
  });

  it('clearTokens is a no-op', async () => {
    await clearTokens();
    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
  });
});
