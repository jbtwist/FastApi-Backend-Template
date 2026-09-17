import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * The address the last verification email went to, plus when it was sent — used
 * by the "verify your email" screen to name the account and to throttle
 * "Resend" client-side (the server also enforces its own limit). Not a secret,
 * so it lives in plain device storage, not the secure store. Cleared once the
 * account is verified or on a successful sign-in to that same account.
 *
 * Every accessor is best-effort and never throws: the record is a convenience,
 * and storage that is blocked or full must not turn an account that was
 * created into a reported failure.
 */
export interface PendingVerification {
  email: string;
  /** epoch ms */
  lastSentAt: number;
}

export const PENDING_VERIFICATION_KEY = 'auth.pendingVerification';

function isPendingVerification(value: unknown): value is PendingVerification {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as PendingVerification).email === 'string' &&
    typeof (value as PendingVerification).lastSentAt === 'number'
  );
}

/**
 * Whether two addresses name the same account. The backend trims and
 * lower-cases every address, while the pending record keeps what was typed.
 */
export function isSameEmail(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

/** Retrieves the `PendingVerification` state from local storage. */
export async function get(): Promise<PendingVerification | null> {
  let raw: string | null;
  try {
    raw = await AsyncStorage.getItem(PENDING_VERIFICATION_KEY);
  } catch {
    return null;
  }
  if (raw == null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isPendingVerification(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Saves the `PendingVerification` state to local storage. */
export async function set(value: PendingVerification): Promise<void> {
  await AsyncStorage.setItem(PENDING_VERIFICATION_KEY, JSON.stringify(value)).catch(
    () => undefined,
  );
}

/** Clears the `PendingVerification` state from local storage. */
export async function clear(): Promise<void> {
  await AsyncStorage.removeItem(PENDING_VERIFICATION_KEY).catch(() => undefined);
}
