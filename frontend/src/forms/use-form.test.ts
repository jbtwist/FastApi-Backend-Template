import { act, renderHook, waitFor } from '@testing-library/react-native';

import { useForm } from './use-form';
import { minLength, required } from './validators';

type Values = { email: string; password: string };

const setup = (onSubmit: (v: Values) => void | Promise<void>) =>
  renderHook(() =>
    useForm<Values>({
      initialValues: { email: '', password: '' },
      validate: { email: [required], password: [required, minLength(12)] },
      onSubmit,
    }),
  );

it('starts empty and idle', () => {
  const { result } = setup(jest.fn());
  expect(result.current.values).toEqual({ email: '', password: '' });
  expect(result.current.errors).toEqual({});
  expect(result.current.touched).toEqual({});
  expect(result.current.formMessage).toBeNull();
  expect(result.current.submitting).toBe(false);
});

it('setValue updates the field and clears its error + the form message', () => {
  const { result } = setup(jest.fn());

  act(() => result.current.setFormMessage({ kind: 'error', text: 'boom' }));
  act(() => result.current.handleBlur('email'));
  expect(result.current.errors.email).toBeDefined();

  act(() => result.current.setValue('email', 'a@b.co'));
  expect(result.current.values.email).toBe('a@b.co');
  expect(result.current.errors.email).toBeUndefined();
  expect(result.current.formMessage).toBeNull();
});

it('setError forces a field error and marks it touched; setValue clears it', () => {
  const { result } = setup(jest.fn());

  act(() => result.current.setError('password', 'Password is too short (minimum 12 characters)'));
  expect(result.current.errors.password).toBe('Password is too short (minimum 12 characters)');
  expect(result.current.touched.password).toBe(true);

  act(() => result.current.setValue('password', 'a-strong-password'));
  expect(result.current.errors.password).toBeUndefined();
});

it('handleBlur marks the field touched and validates just that field', () => {
  const { result } = setup(jest.fn());
  act(() => result.current.handleBlur('password'));
  expect(result.current.touched.password).toBe(true);
  expect(result.current.errors.password).toBeDefined();
  expect(result.current.errors.email).toBeUndefined();
});

it('blocks submit when validation fails: marks every field touched, no onSubmit', async () => {
  const onSubmit = jest.fn();
  const { result } = setup(onSubmit);

  await act(async () => {
    await result.current.handleSubmit();
  });

  expect(onSubmit).not.toHaveBeenCalled();
  expect(result.current.errors.email).toBeDefined();
  expect(result.current.errors.password).toBeDefined();
  expect(result.current.touched).toEqual({ email: true, password: true });
  expect(result.current.submitting).toBe(false);
});

it('submits valid values and toggles submitting around the call', async () => {
  let release: () => void = () => {};
  const onSubmit = jest.fn(
    () =>
      new Promise<void>((resolve) => {
        release = resolve;
      }),
  );
  const { result } = setup(onSubmit);

  act(() => result.current.setValue('email', 'user@example.com'));
  act(() => result.current.setValue('password', 'a-strong-password'));

  let submitPromise: Promise<void>;
  act(() => {
    submitPromise = result.current.handleSubmit();
  });

  await waitFor(() => expect(result.current.submitting).toBe(true));
  expect(onSubmit).toHaveBeenCalledWith({
    email: 'user@example.com',
    password: 'a-strong-password',
  });

  await act(async () => {
    release();
    await submitPromise!;
  });
  expect(result.current.submitting).toBe(false);
});

it('guards against double submit while a submit is in flight', async () => {
  let release: () => void = () => {};
  const onSubmit = jest.fn(
    () => new Promise<void>((resolve) => (release = resolve)),
  );
  const { result } = setup(onSubmit);
  act(() => result.current.setValue('email', 'user@example.com'));
  act(() => result.current.setValue('password', 'a-strong-password'));

  let first: Promise<void>;
  act(() => {
    first = result.current.handleSubmit();
  });
  await waitFor(() => expect(result.current.submitting).toBe(true));
  await act(async () => {
    await result.current.handleSubmit();
  });

  expect(onSubmit).toHaveBeenCalledTimes(1);
  await act(async () => {
    release();
    await first!;
  });
});

it('resets submitting when onSubmit rejects, and surfaces the rejection', async () => {
  const onSubmit = jest.fn().mockRejectedValue(new Error('network'));
  const { result } = setup(onSubmit);
  act(() => result.current.setValue('email', 'user@example.com'));
  act(() => result.current.setValue('password', 'a-strong-password'));

  await act(async () => {
    await expect(result.current.handleSubmit()).rejects.toThrow('network');
  });

  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(result.current.submitting).toBe(false);
});

it('reset() returns to the initial state', () => {
  const { result } = setup(jest.fn());
  act(() => result.current.setValue('email', 'x@y.co'));
  act(() => result.current.setFormMessage({ kind: 'info', text: 'hi' }));
  act(() => result.current.reset());

  expect(result.current.values).toEqual({ email: '', password: '' });
  expect(result.current.formMessage).toBeNull();
});
