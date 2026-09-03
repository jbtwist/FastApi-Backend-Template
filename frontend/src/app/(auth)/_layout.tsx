import { Stack } from 'expo-router/stack';

/**
 * Unauthenticated screens (sign-in, register, verify-email, forgot-password).
 * The "redirect to (app) when already signed in" guard is wired in T032.
 */
export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
