import { useCallback, useMemo, useRef, useState } from 'react';

import type { FormMessageValue } from '@/components/auth/form-message';
import { resolveMessage, type Message } from '@/i18n/message';
import { useTranslation } from '@/i18n/provider';

import type { Validator } from './validators';

/**
 * Options for configuring the `useForm` hook.
 */
export interface UseFormOptions<T extends Record<string, string>> {
  /** The initial state of the form values. */
  initialValues: T;
  /** Ordered validators per field; the first failing message is used. */
  validate?: Partial<Record<keyof T, Validator[]>>;
  /** Called when the form is submitted, if validation passes. */
  onSubmit: (values: T) => void | Promise<void>;
}

/**
 * Result returned by the `useForm` hook.
 */
export interface UseFormResult<T extends Record<string, string>> {
  /** Current form values. */
  values: T;
  /** Current field errors, translated into the active language. */
  errors: Partial<Record<keyof T, string>>;
  /** Tracked fields, keyed by field name. */
  touched: Partial<Record<keyof T, boolean>>;
  /** Form-level message (error/info). */
  formMessage: FormMessageValue | null;
  /** Whether the form is currently submitting. */
  submitting: boolean;
  /** Sets a field's value and clears associated errors. */
  setValue: (field: keyof T, value: string) => void;
  /** Marks a field as touched and validates it. */
  handleBlur: (field: keyof T) => void;
  /** Force a field error (e.g. a server rejection); also marks it touched so it shows. */
  setError: (field: keyof T, message: Message | undefined) => void;
  /** Sets a form-level message. */
  setFormMessage: (message: FormMessageValue | null) => void;
  /** Resets the form to initial state. */
  reset: () => void;
  /** Validates and submits the form, if valid. */
  handleSubmit: () => Promise<void>;
}

function firstError<T extends Record<string, string>>(
  validate: UseFormOptions<T>['validate'],
  field: keyof T,
  value: string,
): Message | undefined {
  for (const validator of validate?.[field] ?? []) {
    const message = validator(value);
    if (message) return message;
  }
  return undefined;
}

/**
 * Tiny form state hook shared by every auth screen: values, per-field errors,
 * `touched`, a form-level banner, and a `submitting` flag that also guards
 * against a double submit. No form library.
 */
export function useForm<T extends Record<string, string>>(
  options: UseFormOptions<T>,
): UseFormResult<T> {
  const { initialValues, validate, onSubmit } = options;

  const { t } = useTranslation();

  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, Message>>>({});
  const [touched, setTouched] = useState<Partial<Record<keyof T, boolean>>>({});
  const [formMessage, setFormMessage] = useState<FormMessageValue | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Ref so the guard is synchronous — two calls in the same tick can't both pass.
  const submittingRef = useRef(false);

  const setValue = useCallback((field: keyof T, value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));
    setFormMessage(null);
  }, []);

  const handleBlur = useCallback(
    (field: keyof T) => {
      setTouched((prev) => ({ ...prev, [field]: true }));
      setValues((current) => {
        setErrors((prev) => ({
          ...prev,
          [field]: firstError(validate, field, current[field]),
        }));
        return current;
      });
    },
    [validate],
  );

  const setError = useCallback((field: keyof T, message: Message | undefined) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    setErrors((prev) => ({ ...prev, [field]: message }));
  }, []);

  const reset = useCallback(() => {
    setValues(initialValues);
    setErrors({});
    setTouched({});
    setFormMessage(null);
    setSubmitting(false);
    submittingRef.current = false;
  }, [initialValues]);

  const handleSubmit = useCallback(async () => {
    if (submittingRef.current) return;

    const nextErrors: Partial<Record<keyof T, Message>> = {};
    const nextTouched: Partial<Record<keyof T, boolean>> = {};
    let hasError = false;
    for (const field of Object.keys(values) as (keyof T)[]) {
      nextTouched[field] = true;
      const message = firstError(validate, field, values[field]);
      if (message) {
        nextErrors[field] = message;
        hasError = true;
      }
    }
    setTouched(nextTouched);

    if (hasError) {
      setErrors(nextErrors);
      return;
    }
    setErrors({});

    submittingRef.current = true;
    setSubmitting(true);
    try {
      // Screens map their own API failures to `formMessage` inside `onSubmit`;
      // an error that still escapes is a bug — reset the flag but let it through.
      await onSubmit(values);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, [onSubmit, validate, values]);

  const translatedErrors = useMemo(() => {
    const resolved: Partial<Record<keyof T, string>> = {};
    for (const [field, message] of Object.entries(errors) as [keyof T, Message | undefined][]) {
      if (message !== undefined) resolved[field] = resolveMessage(t, message);
    }
    return resolved;
  }, [errors, t]);

  return {
    values,
    errors: translatedErrors,
    touched,
    formMessage,
    submitting,
    setValue,
    handleBlur,
    setError,
    setFormMessage,
    reset,
    handleSubmit,
  };
}
