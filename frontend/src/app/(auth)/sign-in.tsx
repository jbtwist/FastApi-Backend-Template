/**
 * Sign in to an existing account.
 *
 * Wraps the shared auth shell around an email + password form. `useAuth().signIn`
 * does the work; this screen only maps its `AuthApiError` outcomes to what the
 * user sees:
 *   401 → combined "email or password" error, password cleared, email kept
 *   403 → the account exists but is unverified — go to the verify screen
 *   422 → a rejected address, shown on the email field
 *   429 / offline / timeout / other → a form-level banner
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import { useAuth } from '@/auth/auth-context';
import type { OAuthProvider } from '@/auth/config';
import { oauthErrorCodeToAuthUiError, type AuthUiError } from '@/auth/errors';
import { fetchEnabledProviders, startOAuthSignIn } from '@/auth/oauth-client';
import { AuthScreen } from '@/components/auth/auth-screen';
import { FormMessage, type FormMessageValue } from '@/components/auth/form-message';
import { PasswordField } from '@/components/auth/password-field';
import { PrimaryButton } from '@/components/auth/primary-button';
import { ProviderButtons } from '@/components/auth/provider-buttons';
import { linkEmailSentMessage, oauthMessageFor } from '@/components/auth/provider-messages';
import { TextField } from '@/components/auth/text-field';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useForm } from '@/forms/use-form';
import { email as emailRule, required } from '@/forms/validators';
import type { Translate } from '@/i18n/message';
import type { TranslationKey } from '@/i18n/types';
import { useTranslation } from '@/i18n/provider';

type SignInValues = { email: string; password: string };

/** Banner copy for the failures that stay on this screen (403 navigates away). */
function messageKeyFor(error: AuthUiError): TranslationKey {
  switch (error.kind) {
    case 'invalid-credentials':
      return 'errors.invalidCredentials';
    case 'rate-limited':
      return 'errors.rateLimited';
    case 'offline':
      return 'errors.offline';
    case 'timeout':
      return 'errors.timeout';
    default:
      return 'errors.unknown';
  }
}

/**
 * The web return leg's one-shot flags: `oauth_error` (with `linked_provider`
 * for `email_linked_to_other_provider`) on a failure, `oauth_notice` when a
 * link email went out instead of a session.
 */
type OAuthReturnParams = {
  oauth_error?: string;
  linked_provider?: string;
  oauth_notice?: string;
};

function oauthReturnMessage(params: OAuthReturnParams, t: Translate): FormMessageValue | null {
  if (params.oauth_error) {
    const ui = oauthErrorCodeToAuthUiError(params.oauth_error, params.linked_provider);
    return ui.kind === 'oauth-cancelled'
      ? null
      : { kind: 'error', message: oauthMessageFor(ui, undefined, t) };
  }
  if (params.oauth_notice === 'link_email_sent') {
    return { kind: 'info', message: linkEmailSentMessage(undefined, t) };
  }
  return null;
}

export default function SignInScreen() {
  const router = useRouter();
  const returnParams = useLocalSearchParams<OAuthReturnParams>();
  const hasReturnFlags = Boolean(
    returnParams.oauth_error || returnParams.linked_provider || returnParams.oauth_notice,
  );
  const { t } = useTranslation();
  const { signIn, signedOutReason, completeOAuthSignIn } = useAuth();

  const [oauthProviders, setOauthProviders] = useState<OAuthProvider[]>([]);
  // Seeded once from the URL the screen was launched with — the web return
  // leg's one-shot flags. A lazy initializer, not an effect: the value only
  // ever matters on the very first render, before the effect below clears the
  // flags from the URL.
  const [oauthMessage, setOauthMessage] = useState<FormMessageValue | null>(() =>
    oauthReturnMessage(returnParams, t),
  );
  const [oauthSubmitting, setOauthSubmitting] = useState(false);
  const oauthSubmittingRef = useRef(false);

  useEffect(() => {
    let active = true;
    fetchEnabledProviders()
      .then((providers) => {
        if (active) setOauthProviders(providers);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  // Clear the one-shot flags so they don't resurface on a manual refresh.
  // Deferred a tick: calling a router navigation method during the very first
  // commit, before the root layout has finished mounting, throws.
  useEffect(() => {
    if (!hasReturnFlags) return;
    const timer = setTimeout(
      () =>
        router.setParams({
          oauth_error: undefined,
          linked_provider: undefined,
          oauth_notice: undefined,
        }),
      0,
    );
    return () => clearTimeout(timer);
  }, [hasReturnFlags, router]);

  const handleProviderSelect = useCallback(
    async (provider: OAuthProvider) => {
      if (oauthSubmittingRef.current) return;
      oauthSubmittingRef.current = true;
      setOauthSubmitting(true);
      setOauthMessage(null);
      try {
        const outcome = await startOAuthSignIn(provider, { onSignedIn: completeOAuthSignIn });
        if (outcome.kind === 'signed-in') {
          router.replace('/');
          return;
        }
        if (outcome.kind === 'link-email-sent') {
          setOauthMessage({ kind: 'info', message: linkEmailSentMessage(provider, t) });
          return;
        }
        if (outcome.kind === 'cancelled' || outcome.kind === 'navigating') return;
        setOauthMessage({ kind: 'error', message: oauthMessageFor(outcome.error, provider, t) });
      } finally {
        oauthSubmittingRef.current = false;
        setOauthSubmitting(false);
      }
    },
    [completeOAuthSignIn, router, t],
  );

  const form = useForm<SignInValues>({
    initialValues: { email: '', password: '' },
    validate: {
      email: [required, emailRule],
      password: [required],
    },
    onSubmit: async ({ email, password }) => {
      try {
        await signIn(email, password);
        router.replace('/');
      } catch (error) {
        if (error instanceof AuthApiError) {
          const ui = error.uiError;
          if (ui.kind === 'email-not-verified') {
            router.replace({
              pathname: '/verify-email',
              params: { email: ui.email || email },
            });
            return;
          }
          if (ui.kind === 'invalid-email') {
            form.setError('email', 'errors.invalidEmail');
            return;
          }
          if (ui.kind === 'invalid-credentials') {
            form.setValue('password', '');
          }
          form.setFormMessage({ kind: 'error', message: messageKeyFor(ui) });
          return;
        }
        form.setFormMessage({ kind: 'error', message: 'errors.unknown' });
      }
    },
  });

  const { values, errors, touched, formMessage, submitting, setValue, handleBlur, handleSubmit } =
    form;

  return (
    <AuthScreen
      title={t('signIn.title')}
      subtitle={t('signIn.subtitle')}
      footer={
        <PrimaryButton
          label={t('signIn.submit')}
          onPress={handleSubmit}
          submitting={submitting}
        />
      }
      dividerSlot={
        <>
          <ProviderButtons
            providers={oauthProviders}
            enabled={!oauthSubmitting}
            onSelect={handleProviderSelect}
          />
          <FormMessage message={oauthMessage} testID="sign-in-oauth-message" />
        </>
      }>
      {signedOutReason ? (
        <FormMessage message={{ kind: 'info', message: 'session.signedOutNotice' }} />
      ) : null}
      <FormMessage message={formMessage} testID="sign-in-form-message" />

      <TextField
        label={t('common.emailLabel')}
        placeholder={t('common.emailPlaceholder')}
        value={values.email}
        onChangeText={(next) => setValue('email', next)}
        onBlur={() => handleBlur('email')}
        error={touched.email ? errors.email : undefined}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="emailAddress"
        keyboardType="email-address"
        returnKeyType="next"
      />

      <PasswordField
        label={t('common.passwordLabel')}
        placeholder={t('common.passwordPlaceholder')}
        value={values.password}
        onChangeText={(next) => setValue('password', next)}
        onBlur={() => handleBlur('password')}
        error={touched.password ? errors.password : undefined}
        returnKeyType="go"
        onSubmitEditing={handleSubmit}
      />

      <View style={styles.links}>
        <Link href="/register">
          <ThemedText type="link" themeColor="tint">
            {t('signIn.createAccount')}
          </ThemedText>
        </Link>
        <Link href="/forgot-password">
          <ThemedText type="link" themeColor="tint">
            {t('signIn.forgotPassword')}
          </ThemedText>
        </Link>
      </View>
    </AuthScreen>
  );
}

const styles = StyleSheet.create({
  links: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: Spacing.one,
  },
});
