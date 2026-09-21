/**
 * Banner copy for a third-party sign-in attempt, shared by every screen that
 * renders provider buttons. Returns a `Message` — keys plus options — so a
 * banner already on screen follows a language switch.
 */
import type { OAuthProvider } from '@/auth/config';
import type { AuthUiError } from '@/auth/errors';
import { PROVIDER_LABEL_KEY } from '@/components/auth/provider-buttons';
import type { Message, Translate } from '@/i18n/message';

/**
 * Banner copy for an oauth failure — `oauth-cancelled` is never shown.
 *
 * `provider` is `undefined` for the web return leg: the redirect's
 * `oauth_error` flag carries no provider identity, so a specific "Google
 * couldn't confirm…" would be a guess and could name the wrong provider.
 * The one provider the flags do name is the account's *existing* one, carried
 * on the error itself as `linkedProvider`.
 */
export function oauthMessageFor(
  error: AuthUiError,
  provider: OAuthProvider | undefined,
  t: Translate,
): Message {
  switch (error.kind) {
    case 'oauth-email-unverified':
      return provider
        ? { key: 'providers.emailNotConfirmed', options: { provider: t(PROVIDER_LABEL_KEY[provider]) } }
        : 'providers.emailNotConfirmedGeneric';
    case 'oauth-unavailable':
      return 'providers.unavailable';
    case 'oauth-not-enabled':
      return 'providers.notEnabled';
    case 'oauth-failed':
      return 'providers.failed';
    case 'oauth-email-linked-elsewhere':
      return error.linkedProvider
        ? {
            key: 'providers.linkedElsewhere',
            options: { provider: t(PROVIDER_LABEL_KEY[error.linkedProvider]) },
          }
        : 'providers.linkedElsewhereGeneric';
    default:
      return 'errors.unknown';
  }
}

/**
 * Info copy for an attempt that ended in a link confirmation email instead of
 * a session. Generic on the web return leg, whose flag names no provider.
 */
export function linkEmailSentMessage(provider: OAuthProvider | undefined, t: Translate): Message {
  return provider
    ? { key: 'providers.linkEmailSent', options: { provider: t(PROVIDER_LABEL_KEY[provider]) } }
    : 'providers.linkEmailSentGeneric';
}
