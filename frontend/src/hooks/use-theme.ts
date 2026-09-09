/**
 * Learn more about light and dark modes:
 * https://docs.expo.dev/guides/color-schemes/
 */

import { Colors } from '@/constants/theme';
import { useActiveColorScheme } from '@/theme/provider';

export function useTheme() {
  return Colors[useActiveColorScheme()];
}
