# Authentication Workflow and Routing

The application implements session-based routing guards to ensure a seamless and secure user authentication experience.

## AuthProvider and Initialization

The entire application is wrapped in an `AuthProvider` (in `RootLayout`). This provider manages the session state, including automatic refreshing of access tokens and handling the initial check (`loading` status) when the app launches.

While the authentication status is `loading`, the app displays a splash screen and withholds the main navigator to prevent flashes of unauthenticated content.

## Routing Gates

Routing is gated based on the authentication status:

- **Authenticated Area (`/(app)`):** If a user is `signedOut`, they are automatically redirected to `/(auth)/sign-in`.
- **Unauthenticated Area (`/(auth)`):** If a user is `signedIn`, they are automatically redirected to `/(app)`.

## Registration, Email Verification, and Password Reset

The authentication workflow supports user registration and password recovery:

1.  **Registration:** The user submits a new account via the `/register` screen.
2.  **Email Verification:** Upon registration, the user is redirected to the `/verify-email` screen. Confirmation happens at the top-level, ungated `/verify-email-confirm` screen.
3.  **Password Reset:** Users can initiate a password reset via the `/(auth)/forgot-password` screen. This sends an email with a reset link pointing to the top-level, ungated `/reset-password` screen, which processes the token, validates the new password, and provides feedback on success or failure.

### Ungated Routes

Specific routes that support deep linking or external access (e.g., `reset-password`, `verify-email-confirm`) operate outside these routing gates and are never automatically redirected, regardless of the user's authentication status.
