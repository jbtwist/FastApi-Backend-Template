/**
 * Form-level banner
 *
 * Renders nothing when `message` is nullish. The text node carries
 * `role="alert"` plus a polite live region so screen readers announce it as it
 * appears.
 *
 * Callers pass a `Message` — a key, not text — and the banner translates it on
 * every render, so a banner already on screen follows a language switch.
 */
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { resolveMessage, type Message } from '@/i18n/message';
import { useTranslation } from '@/i18n/provider';

export type FormMessageKind = 'error' | 'success' | 'info';

export type FormMessageValue = { kind: FormMessageKind; message: Message };

export type FormMessageProps = {
  message: FormMessageValue | null | undefined;
  testID?: string;
};

export function FormMessage({ message, testID }: FormMessageProps) {
  const theme = useTheme();
  const { t } = useTranslation();
  if (!message) return null;

  const palette = {
    error: { fg: theme.danger, border: theme.danger },
    success: { fg: theme.tint, border: theme.tint },
    info: { fg: theme.textSecondary, border: theme.border },
  }[message.kind];

  return (
    <View
      testID={testID}
      style={[
        styles.banner,
        { borderColor: palette.border, backgroundColor: theme.backgroundElement },
      ]}>
      <ThemedText
        type="small"
        role="alert"
        accessibilityLiveRegion="polite"
        style={{ color: palette.fg }}>
        {resolveMessage(t, message.message)}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
  },
});
