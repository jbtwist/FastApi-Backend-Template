/**
 * Create a new account.
 *
 * Enumeration-safe by construction: `useAuth().register` resolves on `204` for
 * both a fresh address and one that already exists, and this screen never
 * branches on which it was — every accepted request lands on `/verify-email`.
 * Only the server-side failures get mapped:
 *   422 → a rejected password on the password field, or a rejected address on
 *         the email field
 *   429 / offline / timeout / other → a form-level banner
 *
 * Every message is this screen's own translated copy; the server's `detail`
 * never reaches the user. That is affordable because the form already rejects
 * both password lengths itself, leaving the breach check as the only rule the
 * server can still fail — so a `password-policy` 422 can be named precisely
 * without reading what the server wrote. See ADR 5.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import { useAuth } from '@/auth/auth-context';
import { authConfig, type OAuthProvider } from '@/auth/config';
import type { AuthUiError } from '@/auth/errors';
import { fetchEnabledProviders, startOAuthSignIn } from '@/auth/oauth-client';
import * as pendingVerification from '@/auth/pending-verification';
import { AuthScreen } from '@/components/auth/auth-screen';
import { FormMessage, type FormMessageValue } from '@/components/auth/form-message';
import { PasswordField } from '@/components/auth/password-field';
import { PrimaryButton } from '@/components/auth/primary-button';
import { ProviderButtons, PROVIDER_LABEL_KEY } from '@/components/auth/provider-buttons';
import { TextField } from '@/components/auth/text-field';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useForm } from '@/forms/use-form';
import { email as emailRule, maxLength, minLength, required } from '@/forms/validators';
import type { Message, Translate } from '@/i18n/message';
import type { TranslationKey } from '@/i18n/types';
import { useTranslation } from '@/i18n/provider';

type RegisterValues = { email: string; password: string };

/** Banner copy for the form-level failures (422 goes on the field instead). */
function messageKeyFor(error: AuthUiError): TranslationKey {
  switch (error.kind) {
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

/** Banner copy for an oauth failure — `oauth-cancelled` is never shown. */
function oauthMessageFor(error: AuthUiError, provider: OAuthProvider, t: Translate): Message {
  switch (error.kind) {
    case 'oauth-email-unverified':
      return { key: 'providers.emailNotConfirmed', options: { provider: t(PROVIDER_LABEL_KEY[provider]) } };
    case 'oauth-unavailable':
      return 'providers.unavailable';
    case 'oauth-not-enabled':
      return 'providers.notEnabled';
    case 'oauth-failed':
      return 'providers.failed';
    default:
      return 'errors.unknown';
  }
}

export default function RegisterScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { register, completeOAuthSignIn } = useAuth();

  const [oauthProviders, setOauthProviders] = useState<OAuthProvider[]>([]);
  const [oauthMessage, setOauthMessage] = useState<FormMessageValue | null>(null);
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

  const handleProviderSelect = useCallback(
    async (provider: OAuthProvider) => {
      if (oauthSubmittingRef.current) return;
      oauthSubmittingRef.current = true;
      setOauthSubmitting(true);
      setOauthMessage(null);
      try {
        const outcome = await startOAuthSignIn(provider, { onSignedIn: completeOAuthSignIn });
        if (outcome.kind === 'signed-in') {
          router.replace('/(app)');
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

  const form = useForm<RegisterValues>({
    initialValues: { email: '', password: '' },
    validate: {
      email: [required, emailRule],
      password: [
        required,
        minLength(authConfig.passwordMinLength),
        maxLength(authConfig.passwordMaxLength),
      ],
    },
    onSubmit: async ({ email, password }) => {
      try {
        await register(email, password);
        // `onSubmit` only ever runs from `handleSubmit` (an event), never during
        // render — the read is stable in the only place it happens.
        // eslint-disable-next-line react-hooks/purity
        await pendingVerification.set({ email: email.trim(), lastSentAt: Date.now() });
        router.replace('/verify-email');
      } catch (error) {
        if (error instanceof AuthApiError) {
          const ui = error.uiError;
          if (ui.kind === 'password-policy') {
            form.setError('password', 'errors.passwordRejected');
            return;
          }
          if (ui.kind === 'invalid-email') {
            form.setError('email', 'errors.invalidEmail');
            return;
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
      title={t('register.title')}
      subtitle={t('register.subtitle')}
      footer={
        <PrimaryButton
          label={t('register.submit')}
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
          <FormMessage message={oauthMessage} testID="register-oauth-message" />
        </>
      }>
      <FormMessage message={formMessage} testID="register-form-message" />

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
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="go"
        onSubmitEditing={handleSubmit}
      />

      <View style={styles.links}>
        <Link href="/sign-in">
          <ThemedText type="link" themeColor="tint">
            {t('register.haveAccount')}
          </ThemedText>
        </Link>
      </View>
    </AuthScreen>
  );
}

const styles = StyleSheet.create({
  links: {
    marginTop: Spacing.one,
  },
});
