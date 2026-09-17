/**
 * Pure field validators for the auth forms.
 *
 * Each returns a `Message` when the value is invalid, or `undefined` when it
 * passes. Compose them in an array per field (see `use-form.ts`); the first
 * message wins.
 *
 * They return a key rather than translated text so a validation error already on
 * screen follows a language switch — see `i18n/message`.
 */
import type { Message } from '@/i18n/message';

/**
 * Validator function type.
 * @param value The raw string value to validate.
 * @returns The message to show if invalid, or `undefined` if valid.
 */
export type Validator = (value: string) => Message | undefined;

/**
 * Validates that a field is not empty or just whitespace.
 * @param value The string value to validate.
 * @returns An error message if empty/whitespace, otherwise `undefined`.
 */
export const required: Validator = (value) =>
  value.trim() === '' ? 'validation.required' : undefined;

// Deliberately permissive: one `@`, a dot in the domain, no spaces. The server
// is the real authority on deliverability.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Validates that a string is a plausible email address.
 * @param value The string value to validate.
 * @returns An error message if invalid, otherwise `undefined`.
 */
export const email: Validator = (value) =>
  EMAIL_RE.test(value.trim()) ? undefined : 'validation.email';

/**
 * Length in Unicode code points, which is how the backend's `len()` counts.
 * `String.length` counts UTF-16 code units, so an emoji would count twice.
 */
const codePointLength = (value: string): number => Array.from(value).length;

/**
 * Creates a validator that checks if a string meets a minimum length requirement.
 * @param n The minimum length required.
 * @returns A Validator function.
 */
export const minLength =
  (n: number): Validator =>
  (value) =>
    codePointLength(value) >= n ? undefined : { key: 'validation.minLength', options: { min: n } };

/**
 * Creates a validator that checks if a string stays within a maximum length.
 * @param n The maximum length allowed.
 * @returns A Validator function.
 */
export const maxLength =
  (n: number): Validator =>
  (value) =>
    codePointLength(value) <= n ? undefined : { key: 'validation.maxLength', options: { max: n } };
