/**
 * Password input for the auth forms — a thin wrapper over `<TextField />`.
 *
 * - masked by default (`secureTextEntry`); a trailing button toggles it
 * - the toggle is a real button for screen readers, labelled "Show password" /
 *   "Hide password" from the locale tree
 * - every `TextField` / `TextInput` prop passes through, and the ref forwards to
 *   the underlying `TextInput`
 */
import { forwardRef, useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, TextInput } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useTranslation } from '@/i18n/provider';

import { TextField, type TextFieldProps } from './text-field';

export type PasswordFieldProps = Omit<TextFieldProps, 'secureTextEntry' | 'trailing'>;

export const PasswordField = forwardRef<TextInput, PasswordFieldProps>(function PasswordField(
  props,
  ref,
) {
  const theme = useTheme();
  const { t } = useTranslation();
  const [revealed, setRevealed] = useState(false);

  const toggleLabel = revealed ? t('common.hidePassword') : t('common.showPassword');

  const toggle: ReactNode = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={toggleLabel}
      hitSlop={Spacing.two}
      onPress={() => setRevealed((v) => !v)}
      style={styles.toggle}>
      <ThemedText type="smallBold" style={{ color: theme.tint }}>
        {toggleLabel}
      </ThemedText>
    </Pressable>
  );

  return (
    <TextField
      ref={ref}
      secureTextEntry={!revealed}
      autoComplete="current-password"
      textContentType="password"
      trailing={toggle}
      {...props}
    />
  );
});

const styles = StyleSheet.create({
  toggle: {
    paddingVertical: Spacing.one,
  },
});
