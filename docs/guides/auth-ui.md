# Using Auth UI Components

The project includes a suite of reusable UI components for authentication screens, designed for consistency and accessibility.

## Components

- `AuthScreen`: A shared shell for all authentication screens. It handles branding, centered layout, scrolling, and keyboard avoidance.
- `PrimaryButton`: The primary call-to-action button. It supports `submitting` and `disabled` states, including a loading spinner and accessibility support for screen readers.
- `FormMessage`: A banner for displaying `error`, `success`, or `info` messages. It uses appropriate `accessibilityLiveRegion` settings to ensure messages are announced by screen readers.
- `ProviderButtons`: A set of buttons for OAuth providers. It automatically renders buttons based on `authConfig.providers`.
- `TextField`: A labelled input for authentication forms. It supports accessibility labels, error message rendering with `role="alert"`, and an optional trailing accessory slot.
- `PasswordField`: A specialized input for password fields. It extends `TextField` by providing a secure input masking (`secureTextEntry`) and a built-in "Show/Hide" toggle button for accessibility.

## Usage

Use these components to build consistent authentication interfaces throughout the application:

```tsx
import { AuthScreen } from '@/components/auth/auth-screen';
import { PrimaryButton } from '@/components/auth/primary-button';
import { FormMessage } from '@/components/auth/form-message';
import { TextField } from '@/components/auth/text-field';
import { PasswordField } from '@/components/auth/password-field';

// In your screen component
<AuthScreen title="Sign In" subtitle="Welcome back!">
  <FormMessage message={errorMessage} />
  
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
