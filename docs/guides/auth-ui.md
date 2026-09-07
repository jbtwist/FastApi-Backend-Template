# Using Auth UI Components

The project includes a suite of reusable UI components for authentication screens, designed for consistency and accessibility.

## Components

- `AuthScreen`: A shared shell for all authentication screens. It handles branding, centered layout, scrolling, and keyboard avoidance.
- `PrimaryButton`: The primary call-to-action button. It supports `submitting` and `disabled` states, including a loading spinner and accessibility support for screen readers.
- `TextField`: A labelled text input for auth forms. It supports accessible error messages, static hint text, and optional trailing accessories.
- `FormMessage`: A banner for displaying `error`, `success`, or `info` messages. It uses appropriate `accessibilityLiveRegion` settings to ensure messages are announced by screen readers.
- `ProviderButtons`: A set of buttons for OAuth providers. It automatically renders buttons based on `authConfig.providers`.

## Usage

Use these components to build consistent authentication interfaces throughout the application:

```tsx
import { AuthScreen } from '@/components/auth/auth-screen';
import { PrimaryButton } from '@/components/auth/primary-button';
import { TextField } from '@/components/auth/text-field';
import { FormMessage } from '@/components/auth/form-message';

// In your screen component
<AuthScreen title="Sign In" subtitle="Welcome back!">
  <FormMessage message={errorMessage} />
  
  <TextField
    label="Email"
    value={email}
    onChangeText={setEmail}
    error={emailError}
    autoComplete="email"
  />
  
  <PrimaryButton label="Sign In" onPress={handleSignIn} submitting={isSubmitting} />
</AuthScreen>
```
