# Welcome to your Expo app 👋

This is an [Expo](https://expo.dev) project created with [`create-expo-app`](https://www.npmjs.com/package/create-expo-app).

## Get started

1. Install dependencies

   ```bash
   npm ci
   ```

   `.npmrc` blocks dependency install scripts and refuses versions published in
   the last three days (needs npm >= 11.10.0). See
   [ADR 6](../docs/architecture/decisions/0006-harden-npm-installs-over-pnpm.md).

2. Start the app

   ```bash
   npx expo start
   ```

### Environment

Copy `.env.example` to `.env` and point `EXPO_PUBLIC_API_URL` at your backend
(`http://localhost:8000` by default).

`EXPO_PUBLIC_PASSWORD_MIN_LENGTH` and `EXPO_PUBLIC_PASSWORD_MAX_LENGTH` must
match the backend's `PASSWORD_STRENGTH` floor (low = 8, medium = 12,
high = 15) and `PASSWORD_MAX_LENGTH`. The register form checks both before
submitting, so the only policy rule the server has left to reject on is the
breach check — which is what lets the app show a translated reason instead of
the server's English one. Leave them out and the defaults (12 / 128) apply.
Expo inlines these at bundle time, so rebuild after changing them.

For the email-verification and password-reset deep links to land back in this
app during local development, the backend's `backend/.env` needs
`FRONTEND_BASE_URL=http://localhost:8081` (the Expo web dev server origin).

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

### Other setup steps

- To set up ESLint for linting, run `npx expo lint`, or follow our guide on ["Using ESLint and Prettier"](https://docs.expo.dev/guides/using-eslint/)
- If you'd like to set up unit testing, follow our guide on ["Unit Testing with Jest"](https://docs.expo.dev/develop/unit-testing/)
- Learn more about the TypeScript setup in this template in our guide on ["Using TypeScript"](https://docs.expo.dev/guides/typescript/)

## Auth email deep links

The email-verification and password-reset emails link to two frontend routes:

- `/verify-email-confirm?token=…`
- `/reset-password?token=…`

**Local development** needs no extra setup — the links open on the Expo web dev
server, and the backend must point at it with `FRONTEND_BASE_URL` in
`backend/.env` (e.g. `http://localhost:8081`). On a device/simulator the
`frontend://` scheme (already set as `expo.scheme`) resolves the same paths.

**Production** — for an email link to open the installed native app instead of a
browser (iOS Universal Links / Android App Links), the production web host must
be wired up in three places:

1. `frontend/app.json`
   - `expo.ios.associatedDomains` → `["applinks:<your-host>"]`
   - `expo.android.intentFilters` → the `autoVerify` VIEW filter for `<your-host>`
     covering `/verify-email-confirm` and `/reset-password`

   Both currently use the placeholder host `auth-template.example.com` — replace
   it with the real host (the same origin as `FRONTEND_BASE_URL`).

2. The web host serves the association files:
   - `https://<your-host>/.well-known/apple-app-site-association` (JSON, no
     extension, `Content-Type: application/json`) listing this app's
     `<TeamID>.<bundleId>` and the two paths.
   - `https://<your-host>/.well-known/assetlinks.json` listing the Android
     package name and the release signing-key SHA-256 fingerprint.

3. Rebuild the native apps after changing `app.json` (`eas build`, or
   `npx expo prebuild --clean` for a local build) — associated-domain and
   intent-filter changes are native and do not ship over OTA updates.

Until step 2 is in place the links still work: they fall back to the web build.

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.
