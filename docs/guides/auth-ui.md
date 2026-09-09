# Using Auth UI Components

The project includes a suite of reusable UI components for authentication screens, designed for consistency and accessibility.

## Components

- `AuthScreen`: A shared shell for all authentication screens. It handles branding, centered layout, scrolling, and keyboard avoidance.
- `PrimaryButton`: The primary call-to-action button. It supports `submitting` and `disabled` states, including a loading spinner and accessibility support for screen readers.
- `TextField`: A labelled text input for auth forms. It supports accessible error messages, static hint text, and optional trailing accessories.
- `FormMessage`: A banner for displaying `error`, `success`, or `info` messages. It uses appropriate `accessibilityLiveRegion` settings to ensure messages are announced by screen readers.
- `ProviderButtons`: A set of buttons for OAuth providers. It automatically renders buttons based on `authConfig.providers`.
- `PasswordField`: A specialized input for password fields. It extends `TextField` by providing a secure input masking (`secureTextEntry`) and a built-in "Show/Hide" toggle button for accessibility.

`AuthScreen` also renders two controls in its header, so every auth screen gets
them without asking:

- `LanguageSwitcher`: The language picker — web only. See [Add a language](add-a-language.md).
- `ThemeSwitcher`: An icon toggle between the light and dark palettes. See [Switch and extend the theme](theming.md).

`FormMessage` takes a translation key rather than text, and translates it on
every render — see [Show an auth error message](auth-error-messages.md) for why
that matters.

## Usage

Use these components to build consistent authentication interfaces throughout the application:

```tsx
import { AuthScreen } from '@/components/auth/auth-screen';
import { PrimaryButton } from '@/components/auth/primary-button';
import { TextField } from '@/components/auth/text-field';
import { FormMessage } from '@/components/auth/form-message';
import { PasswordField } from '@/components/auth/password-field';

// In your screen component
<AuthScreen title={t('signIn.title')} subtitle={t('signIn.subtitle')}>
  {/* A key, not text — the banner translates it on every render. */}
  <FormMessage message={{ kind: 'error', message: 'errors.invalidCredentials' }} />
  
  <TextField 
    label="Email" 
    value={email} 
    onChangeText={setEmail}
    error={emailError}
  />
  <PasswordField 
    label="Password" 
    value={password} 
    onChangeText={setPassword}
    error={passwordError}
  />
  
  <PrimaryButton label="Sign In" onPress={handleSignIn} submitting={isSubmitting} />
</AuthScreen>
```
