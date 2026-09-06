# Native Deep-Linking for Auth Emails

This guide explains how to configure native deep-linking (Universal Links on iOS and App Links on Android) for auth-related email links (email verification and password reset). This allows these links to open directly in the native application rather than a browser.

## Configuration

The configuration is handled in `frontend/app.json`:

- **iOS:** Configure `expo.ios.associatedDomains` with `applinks:<host>`.
- **Android:** Configure `expo.android.intentFilters` with an `autoVerify` VIEW filter for the `<host>` covering `/verify-email-confirm` and `/reset-password`.

The `<host>` placeholder is `auth-template.example.com`. During deployment, this should be replaced with the actual domain used for auth services (the same as the backend's `MAIL_FRONTEND_BASE_URL`).

## Hosting Requirements

For native linking to function, you must host association files at the following endpoints:

- `/.well-known/apple-app-site-association` (iOS)
- `/.well-known/assetlinks.json` (Android)

## Native Rebuild

Any changes to the deep-linking configuration in `app.json` require a rebuild of the native application. Until these association files are properly served, links will fall back to the web build.
