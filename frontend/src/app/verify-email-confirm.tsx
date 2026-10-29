/**
 * Landing screen for the verification link in the email
 * (`{FRONTEND_BASE_URL}/verify-email-confirm?token=…`). Top-level route, no tab
 * chrome, and — like `reset-password` — never gated by the session guards, so a
 * cold start straight from the inbox works.
 *
 * Reads `?token=`, confirms it with `POST /auth/confirm-email`, and reflects the
 * outcome: verified, link invalid/expired, token missing, or — when a different
 * account is already signed in — a prompt to continue as that user or sign out
 * and verify.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { confirmEmail } from '@/auth/auth-api';
import { useAuth } from '@/auth/auth-context';
import * as pendingVerification from '@/auth/pending-verification';
import { AuthScreen } from '@/components/auth/auth-screen';
import { PrimaryButton } from '@/components/auth/primary-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTranslation } from '@/i18n/provider';

type Phase = 'verifying' | 'success' | 'invalid' | 'missing-token' | 'conflict';

export default function VerifyEmailConfirmScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { status, user, signOut } = useAuth();

  const params = useLocalSearchParams<{ token?: string }>();
  const token = typeof params.token === 'string' ? params.token : '';

  const [phase, setPhase] = useState<Phase>(token ? 'verifying' : 'missing-token');
  const startedRef = useRef(false);

  const runConfirm = useCallback(async () => {
    setPhase('verifying');
    try {
      await confirmEmail(token);
      await pendingVerification.clear();
      setPhase('success');
    } catch {
      // 400 invalid-token, or any transport failure — the recovery is the same:
      // ask for a fresh link.
      setPhase('invalid');
    }
  }, [token]);

  useEffect(() => {
    if (startedRef.current || status === 'loading') return;
    startedRef.current = true;

    // No token → the initial phase is already 'missing-token'; nothing to do.
    if (!token) return;

    void (async () => {
      const pending = await pendingVerification.get();
      const otherAccount =
        pending !== null &&
        user !== null &&
        !pendingVerification.isSameEmail(pending.email, user.email);
      if (status === 'signedIn' && otherAccount) {
        setPhase('conflict');
        return;
      }
      await runConfirm();
    })();
  }, [status, token, user, runConfirm]);

  const goHome = useCallback(() => {
    router.replace(status === 'signedIn' ? '/' : '/sign-in');
  }, [router, status]);

  const requestNewEmail = useCallback(() => {
    router.replace('/verify-email');
  }, [router]);

  const signOutAndVerify = useCallback(async () => {
    await signOut();
    await runConfirm();
  }, [signOut, runConfirm]);

  if (phase === 'verifying') {
    return (
      <AuthScreen title={t('verifyEmailConfirm.verifying')}>
        <View style={styles.center}>
          <ActivityIndicator testID="verify-confirm-spinner" />
        </View>
      </AuthScreen>
    );
  }

  if (phase === 'success') {
    return (
      <AuthScreen
        title={t('verifyEmailConfirm.success')}
        footer={<PrimaryButton label={t('verifyEmailConfirm.continue')} onPress={goHome} />}>
        <ThemedText type="default" themeColor="textSecondary">
          {t('verifyEmailConfirm.successBody')}
        </ThemedText>
      </AuthScreen>
    );
  }

  if (phase === 'conflict') {
    const signedInEmail = user?.email ?? '';
    return (
      <AuthScreen
        title={t('verifyEmailConfirm.conflictTitle')}
        footer={
          <View style={styles.actions}>
            <PrimaryButton
              label={t('verifyEmailConfirm.conflictContinueAs', { email: signedInEmail })}
              onPress={() => router.replace('/')}
            />
            <PrimaryButton
              label={t('verifyEmailConfirm.conflictSignOut')}
              onPress={signOutAndVerify}
            />
          </View>
        }>
        <ThemedText type="default" themeColor="textSecondary">
          {t('verifyEmailConfirm.conflictBody', { email: signedInEmail })}
        </ThemedText>
      </AuthScreen>
    );
  }

  // 'invalid' | 'missing-token'
  return (
    <AuthScreen
      title={t('verifyEmailConfirm.invalidTitle')}
      footer={
        <PrimaryButton label={t('verifyEmailConfirm.requestNew')} onPress={requestNewEmail} />
      }>
      <ThemedText type="default" themeColor="textSecondary">
        {phase === 'missing-token'
          ? t('verifyEmailConfirm.missingToken')
          : t('verifyEmailConfirm.invalidBody')}
      </ThemedText>
    </AuthScreen>
  );
}

const styles = StyleSheet.create({
  center: {
    alignItems: 'center',
    paddingVertical: Spacing.four,
  },
  actions: {
    gap: Spacing.three,
  },
});
