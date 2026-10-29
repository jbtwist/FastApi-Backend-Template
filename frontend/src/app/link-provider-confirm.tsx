/**
 * Landing screen for the link in the "confirm your new sign-in method" email
 * (`{FRONTEND_BASE_URL}/link-provider-confirm?token=…`). Sent when someone
 * signs in with a provider whose email already has an account: opening the
 * link proves they own that account. Top-level route, no tab chrome, and never
 * gated by the session guards, so a cold start straight from the inbox works.
 *
 * Reads `?token=`, confirms it with `POST /auth/oauth/link/confirm`, and
 * reflects the outcome: linked, link invalid/expired, token missing, or the
 * account got another provider meanwhile. Confirming doesn't sign in — the
 * person signs in with the provider next.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import { confirmIdentityLink } from '@/auth/auth-api';
import { useAuth } from '@/auth/auth-context';
import type { OAuthProvider } from '@/auth/config';
import { AuthScreen } from '@/components/auth/auth-screen';
import { PrimaryButton } from '@/components/auth/primary-button';
import { PROVIDER_LABEL_KEY } from '@/components/auth/provider-buttons';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTranslation } from '@/i18n/provider';

type Phase =
  | { kind: 'linking' }
  | { kind: 'success' }
  | { kind: 'invalid' }
  | { kind: 'missing-token' }
  | { kind: 'linked-elsewhere'; linkedProvider?: OAuthProvider };

export default function LinkProviderConfirmScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { status } = useAuth();

  const params = useLocalSearchParams<{ token?: string }>();
  const token = typeof params.token === 'string' ? params.token : '';

  const [phase, setPhase] = useState<Phase>(
    token ? { kind: 'linking' } : { kind: 'missing-token' },
  );
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current || status === 'loading' || !token) return;
    startedRef.current = true;

    void (async () => {
      try {
        await confirmIdentityLink(token);
        setPhase({ kind: 'success' });
      } catch (error) {
        const ui = error instanceof AuthApiError ? error.uiError : undefined;
        setPhase(
          ui?.kind === 'oauth-email-linked-elsewhere'
            ? { kind: 'linked-elsewhere', linkedProvider: ui.linkedProvider }
            : { kind: 'invalid' },
        );
      }
    })();
  }, [status, token]);

  const goOn = useCallback(() => {
    router.replace(status === 'signedIn' ? '/' : '/sign-in');
  }, [router, status]);

  const backToSignIn = useCallback(() => {
    router.replace('/sign-in');
  }, [router]);

  if (phase.kind === 'linking') {
    return (
      <AuthScreen title={t('linkProviderConfirm.linking')}>
        <View style={styles.center}>
          <ActivityIndicator testID="link-confirm-spinner" />
        </View>
      </AuthScreen>
    );
  }

  if (phase.kind === 'success') {
    return (
      <AuthScreen
        title={t('linkProviderConfirm.success')}
        footer={<PrimaryButton label={t('linkProviderConfirm.continue')} onPress={goOn} />}>
        <ThemedText type="default" themeColor="textSecondary">
          {t('linkProviderConfirm.successBody')}
        </ThemedText>
      </AuthScreen>
    );
  }

  if (phase.kind === 'linked-elsewhere') {
    return (
      <AuthScreen
        title={t('linkProviderConfirm.linkedElsewhereTitle')}
        footer={
          <PrimaryButton label={t('linkProviderConfirm.backToSignIn')} onPress={backToSignIn} />
        }>
        <ThemedText type="default" themeColor="textSecondary">
          {phase.linkedProvider
            ? t('providers.linkedElsewhere', {
                provider: t(PROVIDER_LABEL_KEY[phase.linkedProvider]),
              })
            : t('providers.linkedElsewhereGeneric')}
        </ThemedText>
      </AuthScreen>
    );
  }

  // 'invalid' | 'missing-token'
  return (
    <AuthScreen
      title={t('linkProviderConfirm.invalidTitle')}
      footer={
        <PrimaryButton label={t('linkProviderConfirm.backToSignIn')} onPress={backToSignIn} />
      }>
      <ThemedText type="default" themeColor="textSecondary">
        {phase.kind === 'missing-token'
          ? t('linkProviderConfirm.missingToken')
          : t('linkProviderConfirm.invalidBody')}
      </ThemedText>
    </AuthScreen>
  );
}

const styles = StyleSheet.create({
  center: {
    alignItems: 'center',
    paddingVertical: Spacing.four,
  },
});
