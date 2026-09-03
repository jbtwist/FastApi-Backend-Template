import { Stack } from 'expo-router/stack';

/**
 * Authenticated area. The "redirect to (auth)/sign-in when signed out".
 */
export default function AppLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
