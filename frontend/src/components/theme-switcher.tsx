/**
 * Icon toggle between the light and dark palettes.
 *
 * One button rather than a pair, because there are exactly two schemes and the
 * icon can carry the state on its own: a sun while the light palette is active,
 * a moon while the dark one is. No "system" option — the app follows the device
 * until the first press, and that is the absence of a choice rather than a third
 * value (see `theme/config`).
 *
 * The icon shows the *current* scheme; the accessibility label says what
 * pressing will do, since an icon alone cannot express that.
 */
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useTranslation } from '@/i18n/provider';
import { MoonIcon, SunIcon } from '@/theme/icons';
import { useColorSchemeChoice } from '@/theme/provider';

export function ThemeSwitcher() {
  const theme = useTheme();
  const { t } = useTranslation();
  const { scheme, setScheme } = useColorSchemeChoice();
  const [hovered, setHovered] = useState(false);

  const dark = scheme === 'dark';
  const Icon = dark ? MoonIcon : SunIcon;

  return (
    <Pressable
      testID="theme-switcher"
      accessibilityRole="switch"
      accessibilityLabel={t(dark ? 'common.themeSwitchToLight' : 'common.themeSwitchToDark')}
      accessibilityState={{ checked: dark }}
      onPress={() => void setScheme(dark ? 'light' : 'dark')}
      onHoverIn={() => setHovered(true)}
      onHoverOut={() => setHovered(false)}
      style={({ pressed }) => [
        styles.button,
        { borderColor: theme.border },
        hovered && { backgroundColor: theme.backgroundElement },
        pressed && { backgroundColor: theme.backgroundSelected },
      ]}>
      <View testID={`theme-switcher-icon-${scheme}`}>
        <Icon color={theme.text} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // Height matches `LanguageSwitcher`'s trigger so the two line up in a header.
  button: {
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'flex-start',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: Spacing.three,
    paddingVertical: Spacing.one,
    paddingHorizontal: Spacing.two,
    cursor: 'pointer',
  },
});
