# 4. Email verification links point to frontend

Date: 2026-09-06

## Status

Accepted

## Context

The system previously used a server-side HTML page for email verification (`GET /auth/confirm-email`), which was served directly by the API. This created a fragmented user experience, as it lacked the styling and state context of the frontend application. It also prevented the frontend from easily showing loading states, success/error feedback, or automatically transitioning the user to a logged-in or dashboard state after verification.

## Decision

All email verification links will point to the frontend application: `{FRONTEND_BASE_URL}/verify-email-confirm?token=...`.

The backend `GET /auth/confirm-email` endpoint has been retired. The frontend application is responsible for consuming the token from the URL, displaying the appropriate UI, and calling the existing `POST /auth/confirm-email` API endpoint to complete the verification process.

## Alternatives considered

- **Server-side HTML (Previous)**: Easier to implement, but poor UX integration with the frontend.
- **Frontend-based verification with automatic API call**: The frontend automatically calls `POST /auth/confirm-email` upon landing on the `/verify-email-confirm` page. This provides a seamless experience for the user.

## Consequences

- The frontend now has full control over the email verification user journey.
- The API is further simplified, moving away from serving HTML pages.
- Frontend must implement the `/verify-email-confirm` route and corresponding API call.
- The `FRONTEND_BASE_URL` configuration must be correctly set in the backend to build the correct verification link.
