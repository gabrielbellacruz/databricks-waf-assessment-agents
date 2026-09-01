/**
 * Score gauge: an SVG arc showing a 0-100 score.
 *
 * Replaces the canvas-gauges widget the pre-React version used - as SVG it
 * scales cleanly, needs no imperative draw call, and is far lighter.
 */

import { css } from '@emotion/react';
import { colors, fontSizes, transitions } from '@/styles/theme';

export interface ScoreGaugeProps {
  /** Score to display, 0-100 */
  percentage: number;
  size?: number;
  /** Accessible label; falls back to the percentage alone */
  label?: string;
}

/** Arc spans 240°, leaving a gap at the bottom */
const ARC_DEGREES = 240;
const START_ANGLE = 150;
const STROKE_WIDTH = 10;

/** Score thresholds, highest first: green / amber / red bands */
const BANDS: readonly { min: number; color: string }[] = [
  { min: 66, color: colors.success },
  { min: 33, color: colors.warning },
  { min: 0, color: colors.error },
];

/**
 * Point on the arc for a given angle, in SVG user units
 */
function polarToCartesian(cx: number, cy: number, radius: number, angleDegrees: number) {
  const radians = (angleDegrees * Math.PI) / 180;
  return { x: cx + radius * Math.cos(radians), y: cy + radius * Math.sin(radians) };
}

/**
 * SVG path for an arc covering `sweep` degrees from the start angle
 */
function describeArc(cx: number, cy: number, radius: number, sweep: number): string {
  const start = polarToCartesian(cx, cy, radius, START_ANGLE);
  const end = polarToCartesian(cx, cy, radius, START_ANGLE + sweep);
  const largeArcFlag = sweep > 180 ? 1 : 0;

  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
}

const wrapperCss = css({
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
});

const valueCss = css({
  position: 'absolute',
  fontSize: fontSizes.xl,
  fontWeight: 700,
  color: colors.neutral800,
  fontVariantNumeric: 'tabular-nums',
});

const arcCss = css({
  transition: `stroke-dasharray ${transitions.base}`,
});

export const ScoreGauge = ({ percentage, size = 130, label }: ScoreGaugeProps) => {
  const clamped = Math.max(0, Math.min(100, percentage));
  const center = size / 2;
  const radius = center - STROKE_WIDTH;
  const color = BANDS.find((band) => clamped >= band.min)?.color ?? colors.error;

  const trackPath = describeArc(center, center, radius, ARC_DEGREES);
  const valuePath = describeArc(center, center, radius, (ARC_DEGREES * clamped) / 100);

  return (
    <div css={wrapperCss} style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={label ?? `${clamped}%`}
      >
        <path
          d={trackPath}
          fill="none"
          stroke={colors.backgroundDark}
          strokeWidth={STROKE_WIDTH}
          strokeLinecap="round"
        />
        {clamped > 0 && (
          <path
            css={arcCss}
            d={valuePath}
            fill="none"
            stroke={color}
            strokeWidth={STROKE_WIDTH}
            strokeLinecap="round"
          />
        )}
      </svg>
      <span css={valueCss} aria-hidden="true">
        {clamped}%
      </span>
    </div>
  );
};
