/**
 * The single call-to-action on every auth screen.
 *
 * While `submitting` it shows a spinner in place of the label and ignores taps. 
 * `disabled` is the same minus the spinner.
 */
import { ActivityIndicator, Pressable, StyleSheet, type PressableProps } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type PrimaryButtonProps = {
  label: string;
  onPress: () => void;
  submitting?: boolean;
  disabled?: boolean;
  testID?: string;
  accessibilityHint?: PressableProps['accessibilityHint'];
};

export function PrimaryButton({
  label,
  onPress,
  submitting = false,
  disabled = false,
  testID,
  accessibilityHint,
}: PrimaryButtonProps) {
  const theme = useTheme();
  const inactive = submitting || disabled;

  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: submitting }}
      disabled={inactive}
      onPress={() => {
        if (inactive) return;
        onPress();
      }}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: theme.tint },
        (inactive || pressed) && styles.dimmed,
      ]}>
      {submitting ? (
        <ActivityIndicator testID="primary-button-spinner" color={theme.background} />
      ) : (
        <ThemedText type="default" style={[styles.label, { color: theme.background }]}>
          {label}
        </ThemedText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderRadius: 10,
    paddingHorizontal: Spacing.four,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dimmed: {
    opacity: 0.6,
  },
  label: {
    fontWeight: '700',
  },
});
