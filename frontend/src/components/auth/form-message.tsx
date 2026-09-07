/**
 * Form-level banner
 *
 * Renders nothing when `message` is nullish. The text node carries
 * `role="alert"` plus a polite live region so screen readers announce it as it
 * appears.
 */
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type FormMessageKind = 'error' | 'success' | 'info';

export type FormMessageValue = { kind: FormMessageKind; text: string };

export type FormMessageProps = {
  message: FormMessageValue | null | undefined;
  testID?: string;
};

export function FormMessage({ message, testID }: FormMessageProps) {
  const theme = useTheme();
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
        {message.text}
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
