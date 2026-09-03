import AppTabs from '@/components/app-tabs';

/**
 * Tab navigator for the authenticated area. `AppTabs` resolves to the native
 * tab bar on iOS/Android and the custom web tab list on web.
 */
export default function TabsLayout() {
  return <AppTabs />;
}
