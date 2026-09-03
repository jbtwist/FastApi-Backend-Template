/**
 * Every user-facing string in the auth flows lives here so the screens stay
 * literal-free and a translator has one file to work from.
 *
 * One language for now (English). `t(key, vars?)` interpolates `{name}`
 * placeholders from `vars`. Keys are flat and dot-namespaced by screen.
 */

export const strings = {
  'common.appName': 'Taskify',
  'common.or': 'or',
  'common.back': 'Back',
  'common.backToSignIn': 'Back to sign in',
  'common.retry': 'Try again',
  'common.emailLabel': 'Email',
  'common.emailPlaceholder': 'you@example.com',
  'common.passwordLabel': 'Password',
  'common.passwordPlaceholder': 'Your password',
  'common.newPasswordLabel': 'New password',
  'common.showPassword': 'Show password',
  'common.hidePassword': 'Hide password',

  'signIn.title': 'Sign in',
  'signIn.subtitle': 'Sign in to your account to continue.',
  'signIn.submit': 'Sign in',
  'signIn.createAccount': 'Create an account',
  'signIn.forgotPassword': 'Forgot password?',

  'register.title': 'Create your account',
  'register.subtitle': 'Enter your email and a password to get started.',
  'register.submit': 'Create account',
  'register.passwordHint':
    'At least {minLength} characters. Common or breached passwords are rejected.',
  'register.haveAccount': 'Already have an account? Sign in',

  'verifyEmail.title': 'Verify your email',
  'verifyEmail.body': 'We sent a verification link to {email}. Open it to finish setting up your account.',
  'verifyEmail.openLinkHint': 'Tap the link in that email on this device to verify.',
  'verifyEmail.alsoHint':
    'You can also sign in or reset your password from here once your email is verified.',
  'verifyEmail.resend': 'Resend email',
  'verifyEmail.resendSent': 'Verification email sent.',
  'verifyEmail.resendCooldown': 'You can resend in {seconds}s.',

  'verifyEmailConfirm.verifying': 'Verifying your email…',
  'verifyEmailConfirm.success': 'Email verified',
  'verifyEmailConfirm.successBody': 'Your email is verified. You can sign in now.',
  'verifyEmailConfirm.invalidTitle': 'This link is invalid or expired',
  'verifyEmailConfirm.invalidBody': 'Request a new verification email and try again.',
  'verifyEmailConfirm.requestNew': 'Request a new email',
  'verifyEmailConfirm.missingToken': 'This verification link is missing its token.',
  'verifyEmailConfirm.conflictTitle': 'A different account is signed in',
  'verifyEmailConfirm.conflictBody':
    'Sign out of the current account before verifying this email.',

  'forgotPassword.title': 'Reset your password',
  'forgotPassword.subtitle': "Enter your email and we'll send a reset link.",
  'forgotPassword.submit': 'Send reset link',
  'forgotPassword.confirmationTitle': 'Check your email',
  'forgotPassword.confirmationBody':
    'If that address has an account, a reset link is on its way.',

  'resetPassword.title': 'Set a new password',
  'resetPassword.subtitle': 'Choose a new password for your account.',
  'resetPassword.submit': 'Save new password',
  'resetPassword.success': 'Password updated',
  'resetPassword.successBody': 'Your password was changed. Sign in with your new password.',
  'resetPassword.invalidTitle': 'This link is invalid or expired',
  'resetPassword.invalidBody': 'Start over to request a new reset link.',
  'resetPassword.startOver': 'Start over',

  'session.signedOutNotice': 'Please sign in again.',
  'session.signOut': 'Sign out',

  'providers.continueWith': 'Continue with {provider}',
  'providers.comingSoon': 'Third-party sign-in is coming soon.',
  'providers.google': 'Google',
  'providers.apple': 'Apple',

  'errors.invalidCredentials': 'Email or password is incorrect.',
  'errors.emailNotVerified': 'Verify your email before signing in.',
  'errors.rateLimited': 'Too many attempts. Please wait a moment and try again.',
  'errors.offline': 'You appear to be offline. Check your connection and try again.',
  'errors.timeout': 'That took too long. Please try again.',
  'errors.unknown': 'Something went wrong. Please try again.',

  'validation.required': 'This field is required.',
  'validation.email': 'Enter a valid email address.',
  'validation.minLength': 'Must be at least {n} characters.',
} as const;

export type StringKey = keyof typeof strings;

export type TemplateVars = Record<string, string | number>;

/**
 * Look up a string by key and fill `{name}` placeholders from `vars`.
 * Unknown placeholders are left untouched.
 */
export function t(key: StringKey, vars?: TemplateVars): string {
  const template = strings[key];
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}
