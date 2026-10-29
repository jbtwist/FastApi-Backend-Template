/**
 * Landing screen for the reset link in the email
 *
 * Reads `?token=`, then:
 *   - no token, or a `400` on submit → invalid-link panel → "start over"
 *   - a session already active → prompt to continue as that user or sign out
 *     and reset (a successful reset revokes every session on the account)
 *   - otherwise a new-password form → `POST /auth/reset-password` → success
 *
 * The form pre-checks both password lengths, so the only policy rule the
 * server can still fail is the breach check, named precisely without reading
 * the server's prose.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import { resetPassword } from '@/auth/auth-api';
import { authConfig } from '@/auth/config';
import { useAuth } from '@/auth/auth-context';
import type { AuthUiError } from '@/auth/errors';
import { AuthScreen } from '@/components/auth/auth-screen';
import { FormMessage } from '@/components/auth/form-message';
import { PasswordField } from '@/components/auth/password-field';
import { PrimaryButton } from '@/components/auth/primary-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useForm } from '@/forms/use-form';
import { maxLength, minLength, required } from '@/forms/validators';
import type { TranslationKey } from '@/i18n/types';
import { useTranslation } from '@/i18n/provider';

type Outcome = 'pending' | 'success' | 'invalid';

type ResetPasswordValues = { password: string };

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

export default function ResetPasswordScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { status, user, signOut } = useAuth();

  const params = useLocalSearchParams<{ token?: string }>();
  const token = typeof params.token === 'string' ? params.token : '';

  const [outcome, setOutcome] = useState<Outcome>(token ? 'pending' : 'invalid');
  const [conflictResolved, setConflictResolved] = useState(false);

  const form = useForm<ResetPasswordValues>({
    initialValues: { password: '' },
    validate: {
      password: [
        required,
        minLength(authConfig.passwordMinLength),
        maxLength(authConfig.passwordMaxLength),
      ],
    },
    onSubmit: async ({ password }) => {
      try {
        await resetPassword({ token, new_password: password });
        await signOut().catch(() => undefined);
        setOutcome('success');
      } catch (error) {
        if (error instanceof AuthApiError) {
          const ui = error.uiError;
          if (ui.kind === 'invalid-token') {
            setOutcome('invalid');
            return;
          }
          if (ui.kind === 'password-policy') {
            form.setError('password', 'errors.passwordRejected');
            return;
          }
          form.setFormMessage({ kind: 'error', message: messageKeyFor(ui) });
          return;
        }
        form.setFormMessage({ kind: 'error', message: 'errors.unknown' });
      }
    },
  });

  if (outcome === 'success') {
    return (
      <AuthScreen
        title={t('resetPassword.success')}
        footer={
          <PrimaryButton
            label={t('common.backToSignIn')}
            onPress={() => router.replace('/sign-in')}
          />
        }>
        <ThemedText type="default" themeColor="textSecondary">
          {t('resetPassword.successBody')}
        </ThemedText>
      </AuthScreen>
    );
  }

  if (outcome === 'invalid') {
    return (
      <AuthScreen
        title={t('resetPassword.invalidTitle')}
        footer={
          <PrimaryButton
            label={t('resetPassword.startOver')}
            onPress={() => router.replace('/forgot-password')}
          />
        }>
        <ThemedText type="default" themeColor="textSecondary">
          {t('resetPassword.invalidBody')}
        </ThemedText>
      </AuthScreen>
    );
  }

  if (status === 'loading') {
    return (
      <AuthScreen title={t('resetPassword.title')}>
        <View style={styles.center}>
          <ActivityIndicator testID="reset-password-spinner" />
        </View>
      </AuthScreen>
    );
  }

  if (status === 'signedIn' && !conflictResolved) {
    const signedInEmail = user?.email ?? '';
    return (
      <AuthScreen
        title={t('resetPassword.conflictTitle')}
        footer={
          <View style={styles.actions}>
            <PrimaryButton
              label={t('resetPassword.conflictContinueAs', { email: signedInEmail })}
              onPress={() => router.replace('/')}
            />
            <PrimaryButton
              label={t('resetPassword.conflictSignOut')}
              onPress={async () => {
                await signOut();
                setConflictResolved(true);
              }}
            />
          </View>
        }>
        <ThemedText type="default" themeColor="textSecondary">
          {t('resetPassword.conflictBody', { email: signedInEmail })}
        </ThemedText>
      </AuthScreen>
    );
  }

  const { values, errors, touched, formMessage, submitting, setValue, handleBlur, handleSubmit } =
    form;

  return (
    <AuthScreen
      title={t('resetPassword.title')}
      subtitle={t('resetPassword.subtitle')}
      footer={
        <PrimaryButton
          label={t('resetPassword.submit')}
          onPress={handleSubmit}
          submitting={submitting}
        />
      }>
      <FormMessage message={formMessage} testID="reset-password-form-message" />

      <PasswordField
        label={t('common.newPasswordLabel')}
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
