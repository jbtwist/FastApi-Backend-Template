import { Redirect } from 'expo-router';
import { Stack } from 'expo-router/stack';

import { useAuth } from '@/auth/auth-context';

/**
 * Authenticated area. A signed-out visitor is redirected to sign-in.
 */
export default function AppLayout() {
  const { status } = useAuth();
  if (status === 'signedOut') {
    return <Redirect href="/(auth)/sign-in" />;
  }
  return <Stack screenOptions={{ headerShown: false }} />;
}
