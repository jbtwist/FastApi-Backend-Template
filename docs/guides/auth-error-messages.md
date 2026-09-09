# Show an auth error message

Auth screens never render text the backend wrote. A failure is classified from
its HTTP status and the endpoint that produced it, and the screen picks its own
translated string. This keeps error text in the user's language, since the
backend has no localisation layer. The reasoning is in
[ADR 5](../architecture/decisions/0005-frontend-owns-auth-error-copy.md).

## Handle a failure on a screen

`api-client` throws `AuthApiError` for every failed call, carrying a typed
`uiError`. Branch on its `kind`, never on any string:

```tsx
try {
  await register(email, password);
} catch (error) {
  if (error instanceof AuthApiError) {
    const ui = error.uiError;
    if (ui.kind === 'invalid-email') {
      form.setError('email', 'errors.invalidEmail');
      return;
    }
    form.setFormMessage({ kind: 'error', message: messageKeyFor(ui) });
    return;
  }
  form.setFormMessage({ kind: 'error', message: 'errors.unknown' });
}
```

Put the message on the field it belongs to when the failure names one, and in
the `FormMessage` banner otherwise. Each screen keeps its own `messageKeyFor`
helper mapping the remaining kinds to keys, so two screens can word the same
failure differently.

## Pass keys, never translated text

Every message that outlives the render that created it is stored as a `Message`
— a key, or a key plus its `%{placeholder}` values — and translated at render
time. Calling `t()` before putting a message into state freezes it in the
language that was active then, so it survives a language switch untranslated
while the rest of the screen updates.

```tsx
form.setError('password', 'errors.passwordRejected');                     // right
form.setError('password', t('errors.passwordRejected'));                  // wrong
setMessage({ kind: 'error', message: { key: 'x.y', options: { n: 3 } } }); // with values
```

`useForm` translates `errors` on the way out and `FormMessage` translates its
own banner, so screens read `errors.password` as a plain string and pass
`formMessage` straight through. Validators return keys for the same reason,
which also keeps them pure — they no longer import `t` at all.

## Add a new error kind

1. Add the variant to `AuthUiError` in `src/auth/errors.ts`. Give it a payload
   only if the screen needs a value the catalogue cannot supply, such as an
   address to echo back or a retry countdown — never a message.
2. Return it from `toAuthUiError` for the right status and
   `AuthEndpointContext`. The same status means different things per endpoint,
   so gate on the context rather than the status alone.
3. Add the key to **both** `src/i18n/locales/en/errors.json` and
   `src/i18n/locales/es/errors.json`. Spanish is type-checked against English,
   so a missing key fails `npm run typecheck`.
4. Map the kind to that key in the screens that can produce it.

## Password rejections need matching bounds

The server applies three password rules and distinguishes them only in English
prose, so `toAuthUiError` reports all three as a single `password-policy` kind.
A screen can still name the reason precisely — but only by ruling the other two
out itself:

```tsx
password: [
  required,
  minLength(authConfig.passwordMinLength),
  maxLength(authConfig.passwordMaxLength),
],
```

With both lengths rejected client-side, the breach check is the only rule the
server has left, so the screen renders `errors.passwordRejected`.

This holds only while `authConfig` matches the server. Set
`EXPO_PUBLIC_PASSWORD_MIN_LENGTH` and `EXPO_PUBLIC_PASSWORD_MAX_LENGTH` to the
backend's `AUTH_PASSWORD_STRENGTH` floor (low = 8, medium = 12, high = 15) and
`AUTH_PASSWORD_MAX_LENGTH`. If they drift, a length rejection is labelled as a
breach.

Any other screen that sets a password — password reset — must apply both
validators for the same reason.
