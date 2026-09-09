/**
 * "Verify your email" — shown after registration and whenever sign-in is
 * blocked pending verification (login `403`).
 *
 * Names the address the link went to (from the `?email=` param, else the stored
 * `pending-verification` record) and offers a throttled "resend". The cooldown
 * is client-side comfort only — the backend enforces its own `3/min`.
 */
import { Link, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import { resendVerification } from '@/auth/auth-api';
import { authConfig } from '@/auth/config';
import type { AuthUiError } from '@/auth/errors';
import * as pendingVerification from '@/auth/pending-verification';
import { AuthScreen } from '@/components/auth/auth-screen';
import { FormMessage, type FormMessageValue } from '@/components/auth/form-message';
import { PrimaryButton } from '@/components/auth/primary-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import type { TranslationKey } from '@/i18n/types';
import { useTranslation } from '@/i18n/provider';

function messageKeyFor(error: AuthUiError): TranslationKey {
  switch (error.kind) {
    case 'invalid-email':
      return 'errors.invalidEmail';
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

export default function VerifyEmailScreen() {
  const { t } = useTranslation();
  const params = useLocalSearchParams<{ email?: string }>();
  const paramEmail = typeof params.email === 'string' ? params.email : '';

  const [email, setEmail] = useState(paramEmail);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<FormMessageValue | null>(null);

  // Fill the address and any live cooldown from the stored record on mount.
  useEffect(() => {
    let active = true;
    void pendingVerification.get().then((pending) => {
      if (!active || !pending) return;
      setEmail((current) => current || pending.email);
      const remaining =
        authConfig.resendCooldownSeconds - Math.floor((Date.now() - pending.lastSentAt) / 1000);
      if (remaining > 0) setSecondsLeft(remaining);
    });
    return () => {
      active = false;
    };
  }, []);

  // Tick the cooldown down to zero.
  useEffect(() => {
    if (secondsLeft <= 0) return;
    const id = setTimeout(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearTimeout(id);
  }, [secondsLeft]);

  const onResend = useCallback(async () => {
    if (!email || sending || secondsLeft > 0) return;
    setSending(true);
    setMessage(null);
    try {
      await resendVerification(email);
      await pendingVerification.set({ email, lastSentAt: Date.now() });
      setMessage({ kind: 'success', message: 'verifyEmail.resendSent' });
      setSecondsLeft(authConfig.resendCooldownSeconds);
    } catch (error) {
      setMessage({
        kind: 'error',
        message: error instanceof AuthApiError ? messageKeyFor(error.uiError) : 'errors.unknown',
      });
    } finally {
      setSending(false);
    }
  }, [email, sending, secondsLeft]);

  return (
    <AuthScreen
      title={t('verifyEmail.title')}
      footer={
        <PrimaryButton
          label={t('verifyEmail.resend')}
          onPress={onResend}
          submitting={sending}
          disabled={!email || secondsLeft > 0}
        />
      }>
      <ThemedText type="default" themeColor="textSecondary">
        {t('verifyEmail.body', { email })}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {t('verifyEmail.openLinkHint')}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {t('verifyEmail.alsoHint')}
      </ThemedText>

      <FormMessage message={message} testID="verify-email-message" />

      {secondsLeft > 0 ? (
        <ThemedText type="small" themeColor="textSecondary" testID="verify-email-cooldown">
          {t('verifyEmail.resendCooldown', { count: secondsLeft })}
        </ThemedText>
      ) : null}

      <View style={styles.links}>
        <Link href="/sign-in">
          <ThemedText type="link" themeColor="tint">
            {t('common.backToSignIn')}
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
