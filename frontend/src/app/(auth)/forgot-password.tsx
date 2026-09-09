/**
 * Request a password-reset link.
 */
import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import { forgotPassword } from '@/auth/auth-api';
import type { AuthUiError } from '@/auth/errors';
import { AuthScreen } from '@/components/auth/auth-screen';
import { FormMessage } from '@/components/auth/form-message';
import { PrimaryButton } from '@/components/auth/primary-button';
import { TextField } from '@/components/auth/text-field';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useForm } from '@/forms/use-form';
import { email as emailRule, required } from '@/forms/validators';
import type { TranslationKey } from '@/i18n/types';
import { useTranslation } from '@/i18n/provider';

type ForgotPasswordValues = { email: string };

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

export default function ForgotPasswordScreen() {
  const { t } = useTranslation();
  const [sent, setSent] = useState(false);

  const form = useForm<ForgotPasswordValues>({
    initialValues: { email: '' },
    validate: { email: [required, emailRule] },
    onSubmit: async ({ email }) => {
      try {
        await forgotPassword(email.trim());
        setSent(true);
      } catch (error) {
        if (error instanceof AuthApiError) {
          const ui = error.uiError;
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

  const backToSignIn = (
    <View style={styles.links}>
      <Link href="/sign-in">
        <ThemedText type="link" themeColor="tint">
          {t('common.backToSignIn')}
        </ThemedText>
      </Link>
    </View>
  );

  if (sent) {
    return (
      <AuthScreen title={t('forgotPassword.confirmationTitle')}>
        <ThemedText type="default" themeColor="textSecondary">
          {t('forgotPassword.confirmationBody')}
        </ThemedText>
        {backToSignIn}
      </AuthScreen>
    );
  }

  const { values, errors, touched, formMessage, submitting, setValue, handleBlur, handleSubmit } =
    form;

  return (
    <AuthScreen
      title={t('forgotPassword.title')}
      subtitle={t('forgotPassword.subtitle')}
      footer={
        <PrimaryButton
          label={t('forgotPassword.submit')}
          onPress={handleSubmit}
          submitting={submitting}
        />
      }>
      <FormMessage message={formMessage} testID="forgot-password-form-message" />

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
        returnKeyType="go"
        onSubmitEditing={handleSubmit}
      />

      {backToSignIn}
    </AuthScreen>
  );
}

const styles = StyleSheet.create({
  links: {
    marginTop: Spacing.one,
  },
});
