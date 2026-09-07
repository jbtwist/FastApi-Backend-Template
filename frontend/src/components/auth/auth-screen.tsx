/**
 * Shared shell for every auth screen: branding header, a single centered card
 * capped at `MaxContentWidth`, scroll + keyboard avoidance so inputs stay
 * visible. Visuals come entirely from theme tokens.
 *
 * `dividerSlot` renders an "or" divider under the card body with the slot
 * content below it — that is where `<ProviderButtons />` (T031) sits.
 */
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useTranslation } from '@/i18n/provider';

export type AuthScreenProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Rendered under the card body, above the divider — e.g. the primary button. */
  footer?: ReactNode;
  /** Optional "or"-divider + slot below the card body. Omit for no divider. */
  dividerSlot?: ReactNode;
};

export function AuthScreen({ title, subtitle, children, footer, dividerSlot }: AuthScreenProps) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();

  return (
    <KeyboardAvoidingView
      style={[styles.flex, { backgroundColor: theme.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + Spacing.five, paddingBottom: insets.bottom + Spacing.five },
        ]}
        keyboardShouldPersistTaps="handled">
        <View style={[styles.card, { maxWidth: MaxContentWidth }]} testID="auth-screen-card">
          <ThemedText type="small" themeColor="tint" style={styles.brand}>
            {t('common.appName')}
          </ThemedText>
          <ThemedText type="subtitle">{title}</ThemedText>
          {subtitle ? (
            <ThemedText type="default" themeColor="textSecondary">
              {subtitle}
            </ThemedText>
          ) : null}

          <View style={styles.body}>{children}</View>
          {footer ? <View style={styles.footer}>{footer}</View> : null}

          {dividerSlot ? (
            <View style={styles.dividerSection} testID="auth-screen-divider">
              <View style={styles.dividerRow}>
                <View style={[styles.rule, { backgroundColor: theme.border }]} />
                <ThemedText type="small" themeColor="textSecondary" style={styles.dividerLabel}>
                  {t('common.or')}
                </ThemedText>
                <View style={[styles.rule, { backgroundColor: theme.border }]} />
              </View>
              {dividerSlot}
            </View>
          ) : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.four,
  },
  card: {
    width: '100%',
    alignSelf: 'center',
    gap: Spacing.three,
  },
  brand: {
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  body: { gap: Spacing.three },
  footer: { gap: Spacing.three },
  dividerSection: { gap: Spacing.three },
  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.three },
  rule: { flex: 1, height: StyleSheet.hairlineWidth },
  dividerLabel: { textTransform: 'lowercase' },
});
