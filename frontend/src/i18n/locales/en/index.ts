/**
 * The canonical English message tree. Every other locale is type-checked
 * against `typeof en` (see `../es/index.ts`), so a missing or misspelt key is
 * a compile error, not a runtime surprise.
 */
import common from './common.json';
import errors from './errors.json';
import forgotPassword from './forgotPassword.json';
import linkProviderConfirm from './linkProviderConfirm.json';
import providers from './providers.json';
import register from './register.json';
import resetPassword from './resetPassword.json';
import session from './session.json';
import signIn from './signIn.json';
import validation from './validation.json';
import verifyEmail from './verifyEmail.json';
import verifyEmailConfirm from './verifyEmailConfirm.json';

export const en = {
  common,
  signIn,
  register,
  verifyEmail,
  verifyEmailConfirm,
  linkProviderConfirm,
  forgotPassword,
  resetPassword,
  session,
  providers,
  errors,
  validation,
} as const;

export type Translations = typeof en;
