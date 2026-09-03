import { Stack } from 'expo-router/stack';

/**
 * Authenticated area. The "redirect to (auth)/sign-in when signed out" guard is
 * wired in T032; for now this is a plain headerless stack around the tab group.
 */
export default function AppLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
