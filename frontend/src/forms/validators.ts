/**
 * Pure field validators for the auth forms.
 * 
 * Each returns an error message when the value is invalid, or `undefined` when it passes.
 * Compose them in an array per field (see `use-form.ts`); the first message wins.
 */
import { t } from '@/i18n';

/**
 * Validator function type.
 * @param value The raw string value to validate.
 * @returns An error message string if invalid, or `undefined` if valid.
 */
export type Validator = (value: string) => string | undefined;

// Messages are looked up per call, not at module load, so a validator created
// before the locale resolves still returns the current language.

/**
 * Validates that a field is not empty or just whitespace.
 * @param value The string value to validate.
 * @returns An error message if empty/whitespace, otherwise `undefined`.
 */
export const required: Validator = (value) =>
  value.trim() === '' ? t('validation.required') : undefined;

// Deliberately permissive: one `@`, a dot in the domain, no spaces. The server
// is the real authority on deliverability.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Validates that a string is a plausible email address.
 * @param value The string value to validate.
 * @returns An error message if invalid, otherwise `undefined`.
 */
export const email: Validator = (value) =>
  EMAIL_RE.test(value.trim()) ? undefined : t('validation.email');

/**
 * Creates a validator that checks if a string meets a minimum length requirement.
 * @param n The minimum length required.
 * @returns A Validator function.
 */
export const minLength =
  (n: number): Validator =>
  (value) =>
    value.length >= n ? undefined : t('validation.minLength', { min: n });
