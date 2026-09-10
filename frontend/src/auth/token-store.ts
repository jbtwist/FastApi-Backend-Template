/**
 * The one place that persists the session token pair on device.
 *
 * Native (iOS / Android): the pair lives in the OS keychain / keystore via
 * `expo-secure-store`. Web: a no-op — the browser holds the session in
 * `httponly`.
 */
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

const ACCESS_KEY = 'auth.accessToken';
const REFRESH_KEY = 'auth.refreshToken';

const isNative = () => Platform.OS !== 'web';

function isValidPair(value: unknown): value is TokenPair {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as TokenPair).accessToken === 'string' &&
    typeof (value as TokenPair).refreshToken === 'string' &&
    (value as TokenPair).accessToken.length > 0 &&
    (value as TokenPair).refreshToken.length > 0
  );
}

/**
 * Read the stored pair. Returns `null` on web, when nothing is stored, when
 * only part of the pair survived, when a value is unreadable, or when secure
 * storage itself throws. A partial / corrupt read also wipes the stray value
 * so the next launch starts clean.
 */
export async function getTokens(): Promise<TokenPair | null> {
  if (!isNative()) return null;

  try {
    const [accessToken, refreshToken] = await Promise.all([
      SecureStore.getItemAsync(ACCESS_KEY),
      SecureStore.getItemAsync(REFRESH_KEY),
    ]);

    const pair = { accessToken, refreshToken };
    if (!isValidPair(pair)) {
      await clearTokens();
      return null;
    }
    return pair;
  } catch {
    await clearTokens().catch(() => undefined);
    return null;
  }
}

/** Persist the pair. No-op on web. Rejects a malformed pair. */
export async function setTokens(tokens: TokenPair): Promise<void> {
  if (!isValidPair(tokens)) {
    throw new Error('setTokens: both accessToken and refreshToken are required');
  }
  if (!isNative()) return;

  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, tokens.accessToken),
    SecureStore.setItemAsync(REFRESH_KEY, tokens.refreshToken),
  ]);
}

/** Remove the pair. No-op on web. Safe to call when nothing is stored. */
export async function clearTokens(): Promise<void> {
  if (!isNative()) return;

  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ]);
}
