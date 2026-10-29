import { Redirect } from 'expo-router';
import { Stack } from 'expo-router/stack';

import { useAuth } from '@/auth/auth-context';

/**
 * Unauthenticated screens (sign-in, register, verify-email, forgot-password).
 * An already-signed-in visitor is bounced into the app.
 */
export default function AuthLayout() {
  const { status } = useAuth();
  if (status === 'signedIn') {
    return <Redirect href="/" />;
  }
  return <Stack screenOptions={{ headerShown: false }} />;
}
