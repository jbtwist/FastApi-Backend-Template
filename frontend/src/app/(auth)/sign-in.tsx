/**
 * Sign in to an existing account.
 *
 * Wraps the shared auth shell around an email + password form. `useAuth().signIn`
 * does the work; this screen only maps its `AuthApiError` outcomes to what the
 * user sees:
 *   401 → combined "email or password" error, password cleared, email kept
 *   403 → the account exists but is unverified — go to the verify screen
 *   429 / offline / timeout / other → a form-level banner
 */
import { Link, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { AuthApiError } from '@/auth/api-client';
import type { AuthUiError } from '@/auth/errors';
import { useAuth } from '@/auth/auth-context';
import { AuthScreen } from '@/components/auth/auth-screen';
import { FormMessage } from '@/components/auth/form-message';
import { PasswordField } from '@/components/auth/password-field';
import { PrimaryButton } from '@/components/auth/primary-button';
import { ProviderButtons } from '@/components/auth/provider-buttons';
import { TextField } from '@/components/auth/text-field';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useForm } from '@/forms/use-form';
import { email as emailRule, required } from '@/forms/validators';
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

export default function SignInScreen() {
  const router = useRouter();
  const { t } = useTranslation();
  const { signIn, signedOutReason } = useAuth();

  const form = useForm<SignInValues>({
    initialValues: { email: '', password: '' },
    validate: {
      email: [required, emailRule],
      password: [required],
    },
    onSubmit: async ({ email, password }) => {
      try {
        await signIn(email, password);
        router.replace('/(app)');
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
          if (ui.kind === 'invalid-credentials') {
            form.setValue('password', '');
          }
          form.setFormMessage({ kind: 'error', text: t(messageKeyFor(ui)) });
          return;
        }
        form.setFormMessage({ kind: 'error', text: t('errors.unknown') });
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
      dividerSlot={<ProviderButtons />}>
      {signedOutReason ? (
        <FormMessage message={{ kind: 'info', text: t('session.signedOutNotice') }} />
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
