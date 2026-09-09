/** The two palettes in `constants/theme`, and the values the switcher offers. */
export const COLOR_SCHEMES = ['light', 'dark'] as const;

export type ColorScheme = (typeof COLOR_SCHEMES)[number];

/**
 * AsyncStorage key holding the user's explicit choice.
 *
 * Absent means "follow the device", which is the default and the only way to be
 * in that state — the switcher offers light and dark, never "system", so a user
 * who has never chosen keeps following the OS and one who has chosen stays
 * pinned until they pick the other.
 */
export const COLOR_SCHEME_STORAGE_KEY = 'taskify.colorScheme';

export function isColorScheme(value: string | null | undefined): value is ColorScheme {
  return !!value && (COLOR_SCHEMES as readonly string[]).includes(value);
}
