/**
 * Labelled text input for the auth forms.
 *
 * - `label` doubles as the input's `accessibilityLabel` unless one is passed.
 * - `error` renders below the field as a polite live-region alert and sets
 *   `aria-invalid` on the input so screen readers announce the problem.
 * - every other `TextInput` prop (`autoComplete`, `textContentType`,
 *   `keyboardType`, `secureTextEntry`, …) passes straight through, and the ref
 *   forwards to the underlying `TextInput`.
 */
import { forwardRef, type ReactNode } from 'react';
import {
  StyleSheet,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type TextFieldProps = Omit<TextInputProps, 'style'> & {
  label: string;
  /** Field-level error; shown below the input and announced to screen readers. */
  error?: string;
  /** Static helper text shown below the input when there is no error. */
  hint?: string;
  /** Rendered inside the input row after the field — e.g. a show/hide toggle. */
  trailing?: ReactNode;
  containerStyle?: StyleProp<ViewStyle>;
  inputStyle?: StyleProp<TextStyle>;
};

export const TextField = forwardRef<TextInput, TextFieldProps>(function TextField(
  { label, error, hint, trailing, containerStyle, inputStyle, accessibilityLabel, ...inputProps },
  ref,
) {
  const theme = useTheme();
  const hasError = Boolean(error);

  return (
    <View style={[styles.container, containerStyle]}>
      <ThemedText type="smallBold" style={styles.label}>
        {label}
      </ThemedText>

      <View
        style={[
          styles.inputRow,
          {
            backgroundColor: theme.inputBackground,
            borderColor: hasError ? theme.danger : theme.border,
          },
        ]}>
        <TextInput
          ref={ref}
          accessibilityLabel={accessibilityLabel ?? label}
          aria-invalid={hasError}
          placeholderTextColor={theme.textSecondary}
          style={[styles.input, { color: theme.text }, inputStyle]}
          {...inputProps}
        />
        {trailing ? <View style={styles.trailing}>{trailing}</View> : null}
      </View>

      {hasError ? (
        <ThemedText
          type="small"
          role="alert"
          accessibilityLiveRegion="polite"
          style={[styles.message, { color: theme.danger }]}>
          {error}
        </ThemedText>
      ) : hint ? (
        <ThemedText type="small" themeColor="textSecondary" style={styles.message}>
          {hint}
        </ThemedText>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    gap: Spacing.one,
  },
  label: {
    marginBottom: Spacing.half,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    minHeight: 48,
  },
  input: {
    flex: 1,
    paddingVertical: Spacing.two,
    fontSize: 16,
  },
  trailing: {
    marginLeft: Spacing.two,
  },
  message: {
    marginTop: Spacing.half,
  },
});
