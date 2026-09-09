# Authentication Workflow and Routing

The application implements session-based routing guards to ensure a seamless and secure user authentication experience.

## AuthProvider and Initialization

The entire application is wrapped in an `AuthProvider` (in `RootLayout`). This provider manages the session state, including automatic refreshing of access tokens and handling the initial check (`loading` status) when the app launches.

While the authentication status is `loading`, the app displays a splash screen and withholds the main navigator to prevent flashes of unauthenticated content.

## Routing Gates

Routing is gated based on the authentication status:

- **Authenticated Area (`/(app)`):** If a user is `signedOut`, they are automatically redirected to `/(auth)/sign-in`.
- **Unauthenticated Area (`/(auth)`):** If a user is `signedIn`, they are automatically redirected to `/(app)`.

## Registration and Email Verification

The registration process involves three steps:

1.  **Registration:** The user submits a new account via the `/register` screen. This endpoint is enumeration-safe, returning the same response regardless of whether the email is already registered.
2.  **Verification Notice:** Upon successful registration, the user is redirected to the `/verify-email` screen, which prompts them to check their email.
3.  **Confirmation:** The user clicks the link in their verification email, which directs them to the top-level, ungated `/verify-email-confirm` screen to complete the activation process.

### Ungated Routes

Specific routes that support deep linking or external access (e.g., `reset-password`, `verify-email-confirm`) operate outside these routing gates and are never automatically redirected, regardless of the user's authentication status.

## Password Reset

1.  **Request:** The user submits their email address via the `/forgot-password` screen. This endpoint is enumeration-safe, returning the same response regardless of whether the email is registered or verified.
2.  **Email Notice:** The user is directed to the "check your email" panel, which confirms the request was processed without revealing whether the email exists.
3.  **Reset:** The user clicks the link in the emailed password reset link, which leads them to the frontend's `/reset-password` screen to define their new password.
