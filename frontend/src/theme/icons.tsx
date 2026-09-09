/**
 * The two scheme icons, drawn as SVG so they stay sharp at any size and take
 * their colour from the active palette.
 *
 * Each is stroked rather than filled, so a single `color` matches the
 * surrounding text in either theme.
 */
import Svg, { Circle, Path } from 'react-native-svg';

export type SchemeIconProps = {
  size?: number;
  color: string;
};

const DEFAULT_SIZE = 18;
const STROKE_WIDTH = 1.8;

/** Sun: a disc with eight rays. Shown while the light palette is active. */
export function SunIcon({ size = DEFAULT_SIZE, color }: SchemeIconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={4.2} stroke={color} strokeWidth={STROKE_WIDTH} />
      <Path
        d="M12 2.4v2.6M12 19v2.6M4.4 12H1.8M22.2 12h-2.6M6.3 6.3 4.5 4.5M19.5 19.5l-1.8-1.8M17.7 6.3l1.8-1.8M4.5 19.5l1.8-1.8"
        stroke={color}
        strokeWidth={STROKE_WIDTH}
        strokeLinecap="round"
      />
    </Svg>
  );
}

/** Crescent moon. Shown while the dark palette is active. */
export function MoonIcon({ size = DEFAULT_SIZE, color }: SchemeIconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M20.5 14.9A8.6 8.6 0 0 1 9.1 3.5a8.6 8.6 0 1 0 11.4 11.4Z"
        stroke={color}
        strokeWidth={STROKE_WIDTH}
        strokeLinejoin="round"
      />
    </Svg>
  );
}
