import type { Translations } from './locales';

export type { Translations };

/** i18n-js plural buckets — an object made only of these is a message, not a group. */
type PluralKey = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

/**
 * Every addressable message path in the tree, dot-joined:
 * `'signIn.title'`, `'errors.passwordRejected'`, `'verifyEmail.resendCooldown'`.
 * A pluralised leaf (`{ one, other }`) yields the path to the object itself,
 * not to its buckets.
 */
type LeafPaths<T> = {
  [K in keyof T & string]: T[K] extends string
    ? K
    : T[K] extends Record<string, unknown>
      ? [keyof T[K] & string] extends [PluralKey]
        ? K
        : `${K}.${LeafPaths<T[K]>}`
      : never;
}[keyof T & string];

export type TranslationKey = LeafPaths<Translations>;
