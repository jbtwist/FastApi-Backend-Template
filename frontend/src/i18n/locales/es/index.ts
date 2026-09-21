/**
 * Spanish messages. Typed as `Translations` (the English tree's shape), so
 * `tsc` fails the build if a namespace or key is missing, misspelt, or extra.
 */
import type { Translations } from '../en';
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

export const es: Translations = {
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
};
