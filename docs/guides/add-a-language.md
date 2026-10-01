# Add a language

The app ships English and Spanish. Adding a third is four files and a flag; the
type system enumerates the rest.

## 1. Declare the locale

Add the code to `SUPPORTED_LOCALES` in `frontend/src/i18n/config.ts`, and its
name **in its own language** to `LOCALE_LABELS`:

```ts
export const SUPPORTED_LOCALES = ['en', 'es', 'fr'] as const;

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
};
```

Labels are endonyms and are never translated. Someone looking for their own
language scans for the word they recognise, which is not its English or Spanish
name.

## 2. Write the catalogue

Copy `frontend/src/i18n/locales/en/` to `locales/<code>/` and translate the
values. One JSON file per namespace; keep the filenames and key names identical.
Then register it in `locales/index.ts`:

```ts
import { fr } from './fr';

export const messages = { en, es, fr };
```

Every locale is type-checked against `typeof en`, so a missing or misspelt key
fails `npm run typecheck` rather than rendering blank at runtime. Interpolate
with `%{name}` and pluralise with `{ count }`.

## 3. Draw the flag

Add an SVG component to `frontend/src/i18n/flags.tsx` and register it in
`FLAG_BY_LOCALE`. That map is keyed by `Locale`, so **this step is not
optional** — skipping it is a compile error, not a blank space in the picker.

SVG rather than emoji flags, which Windows renders as two letters. Keep the
component's `viewBox` at the flag's real aspect ratio and derive its height from
the `width` prop.

Flags are decorative and hidden from assistive technology. A flag names a
country, not a language — Spanish is spoken far beyond Spain — so the endonym
stays the real label, and a screen reader announcing "United Kingdom" for
"English" would be wrong.

## 4. Check the picker still fits

`LanguageSwitcher` is a trigger plus a scrolling list, so it absorbs new
languages without changing the header's width. Past about six the list scrolls;
nothing needs adjusting.

## How the active language is decided

`LocaleProvider` resolves it once on mount:

1. the user's stored choice (`backend-template.locale` in AsyncStorage), if any;
2. otherwise the first device-preferred language the app ships messages for;
3. otherwise `DEFAULT_LOCALE`.

The picker is mounted on web only. A browser's language list is a global setting
a visitor won't change for one site, so the app has to offer the choice itself;
native follows the device language, which the user already controls per-app in
the OS settings.

## Using translations in code

```tsx
const { t } = useTranslation();     // components — re-renders on switch
import { t } from '@/i18n';         // non-component code, one-off lookups
```

`TranslationKey` is derived from the English tree, so keys autocomplete and a
typo fails the build.

Anything that outlives the render that created it — a field error, a banner —
must hold a `Message` (a key, or a key plus its options) rather than the output
of `t()`. Resolving early freezes the string in the language that was active at
the time, so it sits there untranslated after a switch while the rest of the
screen updates:

```tsx
form.setError('password', 'errors.passwordRejected');                     // right
form.setError('password', t('errors.passwordRejected'));                  // wrong
setMessage({ kind: 'error', message: { key: 'x.y', options: { n: 3 } } }); // with values
```

`useForm` translates its `errors` on the way out and `FormMessage` translates
its own banner, so screens read `errors.password` as a plain string and pass
`formMessage` straight through. Validators in `forms/validators.ts` return keys
for the same reason, which also keeps them pure — they never import `t`.
