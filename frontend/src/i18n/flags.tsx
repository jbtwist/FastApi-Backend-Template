/**
 * A flag per supported locale, drawn as SVG so it stays sharp at any size and
 * looks the same on every platform — unlike emoji flags, which Windows refuses
 * to render as flags at all.
 *
 * A flag identifies a language here, not a country, and the two never map
 * cleanly: Spanish is spoken far beyond Spain, and English beyond the UK. The
 * flag is decorative for that reason — every row also carries the language's
 * own name, which is what a reader actually scans for, and the flag is hidden
 * from screen readers.
 *
 * `FLAG_BY_LOCALE` is keyed by `Locale`, so adding a language to
 * `SUPPORTED_LOCALES` without drawing its flag is a compile error.
 */
import Svg, { ClipPath, Defs, G, Path, Rect } from 'react-native-svg';

import type { Locale } from './config';

export type FlagProps = {
  /** Width in px. Height follows the flag's own aspect ratio. */
  width?: number;
};

const DEFAULT_WIDTH = 24;

/** Union Flag, 60×30. */
function FlagEN({ width = DEFAULT_WIDTH }: FlagProps) {
  return (
    <Svg width={width} height={width / 2} viewBox="0 0 60 30">
      <Defs>
        <ClipPath id="uk-diagonals">
          <Path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
        </ClipPath>
      </Defs>
      <Rect width={60} height={30} fill="#012169" />
      <Path d="M0,0 L60,30 M60,0 L0,30" stroke="#FFFFFF" strokeWidth={6} />
      <G clipPath="url(#uk-diagonals)">
        <Path d="M0,0 L60,30 M60,0 L0,30" stroke="#C8102E" strokeWidth={4} />
      </G>
      <Path d="M30,0 V30 M0,15 H60" stroke="#FFFFFF" strokeWidth={10} />
      <Path d="M30,0 V30 M0,15 H60" stroke="#C8102E" strokeWidth={6} />
    </Svg>
  );
}

/** Bandera de España, 3:2, without the coat of arms. */
function FlagES({ width = DEFAULT_WIDTH }: FlagProps) {
  return (
    <Svg width={width} height={(width * 2) / 3} viewBox="0 0 60 40">
      <Rect width={60} height={40} fill="#AA151B" />
      <Rect y={10} width={60} height={20} fill="#F1BF00" />
    </Svg>
  );
}

export const FLAG_BY_LOCALE: Record<Locale, (props: FlagProps) => React.ReactElement> = {
  en: FlagEN,
  es: FlagES,
};
