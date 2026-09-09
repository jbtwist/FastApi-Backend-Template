# 5. The frontend owns all auth error copy

Date: 2026-09-09

## Status

Accepted

## Context

The app ships can be translated to several languages and, but auth failures do 
not follow them. The register screen put the server's `detail` string straight 
onto the password field, so a user reading the app in a diffrent language
who chose a breached password got the error message in English prose
from `backend/src/backend/auth/router.py`, in the middle of a translated form.

The backend has no localisation layer, and giving it one would mean it had to
know the caller's language and carry a message catalogue per client. Its `detail`
strings are written for API consumers and logs, not for end users.

Two facts shape the options. First, the client can distinguish most failures
without reading any prose: the HTTP status plus the endpoint that produced it is
enough, which is what `toAuthUiError` already does. Second, exactly one case
resists that — a `422` from the password policy, where the server has three
rules (too short, too long, breached) and separates them only in the wording of
`detail`.

## Decision

No server-written text is ever rendered. `toAuthUiError` classifies a failure
from its status and endpoint context alone, reading `detail` only for its
*shape* (a list is FastAPI's own schema violation and names the offending
field). Screens map the resulting `AuthUiError` kind to a key in
`i18n/locales`.

To keep the one ambiguous case precise rather than vague, the register form
validates both password length bounds itself, against
`authConfig.passwordMinLength` and `authConfig.passwordMaxLength`. A password
that clears both can only be rejected by the remaining rule, so a
`password-policy` `422` is rendered as the breach message specifically.

Those bounds are read from `EXPO_PUBLIC_PASSWORD_MIN_LENGTH` and
`EXPO_PUBLIC_PASSWORD_MAX_LENGTH` so that retuning the policy is a configuration
change on both sides rather than a code change.

## Alternatives considered

- **Localise the API itself** — give the backend a message catalogue per locale
  and have it negotiate the caller's language (`Accept-Language`, or an explicit
  parameter), so `detail` arrives already translated and the client can go on
  rendering it verbatim. This is the direct fix for the root cause, and the right
  answer for an API whose errors are genuinely prose. Rejected because the effort
  is out of proportion to what it buys here: it means a second catalogue to keep
  in sync with the frontend's, language negotiation on every endpoint, and tests
  per locale — all to translate a handful of strings, when the status and
  endpoint context already identify almost every failure without any prose at
  all. Worth revisiting only if the API grows errors that carry information no
  status code can express.
- **Match the server's prose in the client** (`/too short/`, `/data breach/` →
  a translation key) — keeps all three reasons distinct with no backend change,
  and the existing assertions in `backend/tests/auth/test_router.py` already pin
  two of those substrings. Rejected because it makes the backend's user-facing
  wording load-bearing for the frontend: an editorial change to a message
  silently degrades the UI to a fallback, with nothing failing to catch it.
- **One generic message for every password rejection** — simplest, no coupling
  at all. Rejected because "this password is not allowed" leaves the user with
  no idea what to change, and the breach case is precisely the one where the
  reason is worth stating.
- **Machine-readable error codes from the backend** (`{"detail": {"code":
  "password_compromised"}}`) — the most robust option, and the one to revisit if
  a third client appears or the policy grows more rules. Rejected for now as
  disproportionate: it changes the API contract and its tests to disambiguate a
  case the client can already rule out on its own.
- **Run the breach check client-side too** (Have I Been Pwned's k-anonymity
  range API, as `HIBPPwnedPasswordChecker` does) — would let the app reject a
  breached password before submitting, with its own copy. Rejected as a separate
  concern: it needs a SHA-1 dependency (`expo-crypto`) and it exposes every
  registering user's IP to a third party, which the current server-side check
  does not. It would also not remove the `422` path, since the client check
  fails open.

## Consequences

- Every auth message follows the app's language, and adding a locale needs no
  backend involvement.
- Messages are held as keys, not text, wherever they outlive the render that
  created them — `useForm`'s field errors, `FormMessage`'s banner, and the values
  validators return. Resolving to a string on the way into state would freeze a
  message in the language that was active when it appeared, leaving it stranded
  in the old language after a switch while the rest of the screen updates.
  `useForm` and `FormMessage` translate on the way out instead.
- The backend's `detail` strings are free to change; nothing in the client reads
  them.
- `authConfig`'s two bounds must match the server's `AUTH_PASSWORD_STRENGTH`
  floor (low = 8, medium = 12, high = 15) and `AUTH_PASSWORD_MAX_LENGTH`. If
  they drift, a length rejection reaches the screen and is labelled as a breach
  — wrong copy, though the server still enforces the real rule. `.env.example`
  and `frontend/README.md` state the constraint.
- Expo inlines `EXPO_PUBLIC_*` at bundle time, so a build already installed on a
  device keeps the bounds it was built with. Tightening the server policy
  requires shipping a new build to keep the messages accurate.
- Any future screen that sets a password — password reset, the other endpoint in
  `PASSWORD_POLICY_CONTEXTS` — must apply the same two length validators, or its
  `422` copy will be wrong for the same reason.
