/**
 * A message held as data rather than as text.
 *
 * Anything that survives across renders — a field error, a banner — must store
 * one of these instead of the output of `t()`. Resolving at the moment a message
 * is *created* freezes it in whatever language was active then, so the string
 * outlives the language it was written in: switch locale and the rest of the
 * screen re-renders while that one message stays behind.
 *
 * Resolve with {@link resolveMessage} at render time, from the `t` that
 * `useTranslation()` hands out.
 */
import type { TranslateOptions } from 'i18n-js';

import type { TranslationKey } from './types';

/** A key on its own, or a key plus the values its `%{placeholders}` need. */
export type Message = TranslationKey | { key: TranslationKey; options: TranslateOptions };

export type Translate = (key: TranslationKey, options?: TranslateOptions) => string;

/** Render a {@link Message} in the language `t` is currently bound to. */
export function resolveMessage(t: Translate, message: Message): string {
  return typeof message === 'string' ? t(message) : t(message.key, message.options);
}
