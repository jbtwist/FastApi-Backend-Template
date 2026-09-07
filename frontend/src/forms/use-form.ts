import { useCallback, useRef, useState } from 'react';

import type { FormMessageValue } from '@/components/auth/form-message';

import type { Validator } from './validators';

export interface UseFormOptions<T extends Record<string, string>> {
  initialValues: T;
  /** Ordered validators per field; the first failing message is used. */
  validate?: Partial<Record<keyof T, Validator[]>>;
  onSubmit: (values: T) => void | Promise<void>;
}

export interface UseFormResult<T extends Record<string, string>> {
  values: T;
  errors: Partial<Record<keyof T, string>>;
  touched: Partial<Record<keyof T, boolean>>;
  formMessage: FormMessageValue | null;
  submitting: boolean;
  setValue: (field: keyof T, value: string) => void;
  handleBlur: (field: keyof T) => void;
  setFormMessage: (message: FormMessageValue | null) => void;
  reset: () => void;
  handleSubmit: () => Promise<void>;
}

function firstError<T extends Record<string, string>>(
  validate: UseFormOptions<T>['validate'],
  field: keyof T,
  value: string,
): string | undefined {
  for (const validator of validate?.[field] ?? []) {
    const message = validator(value);
    if (message) return message;
  }
  return undefined;
}

/**
 * Tiny form state hook shared by every auth screen: values, per-field errors,
 * `touched`, a form-level banner, and a `submitting` flag that also guards
 * against a double submit (spec FR-004, SC-011). No form library.
 */
export function useForm<T extends Record<string, string>>(
  options: UseFormOptions<T>,
): UseFormResult<T> {
  const { initialValues, validate, onSubmit } = options;

  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});
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

    const nextErrors: Partial<Record<keyof T, string>> = {};
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

  return {
    values,
    errors,
    touched,
    formMessage,
    submitting,
    setValue,
    handleBlur,
    setFormMessage,
    reset,
    handleSubmit,
  };
}
