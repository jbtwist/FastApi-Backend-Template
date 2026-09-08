# Authentication Workflow and Routing

The application implements session-based routing guards to ensure a seamless and secure user authentication experience.

## AuthProvider and Initialization

The entire application is wrapped in an `AuthProvider` (in `RootLayout`). This provider manages the session state, including automatic refreshing of access tokens and handling the initial check (`loading` status) when the app launches.

While the authentication status is `loading`, the app displays a splash screen and withholds the main navigator to prevent flashes of unauthenticated content.

## Routing Gates

Routing is gated based on the authentication status:

- **Authenticated Area (`/(app)`):** If a user is `signedOut`, they are automatically redirected to `/(auth)/sign-in`.
- **Unauthenticated Area (`/(auth)`):** If a user is `signedIn`, they are automatically redirected to `/(app)`.

### Ungated Routes

Specific routes that support deep linking or external access (e.g., `reset-password`, `verify-email-confirm`) operate outside these routing gates and are never automatically redirected, regardless of the user's authentication status.
