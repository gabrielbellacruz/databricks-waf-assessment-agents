/**
 * Horizontal progress bar.
 */

import { css } from '@emotion/react';
import { colors, radius, transitions } from '@/styles/theme';

export interface ProgressBarProps {
  /** Fill percentage, 0-100 */
  percentage: number;
  /** Fill colour; defaults to Lava 600 */
  color?: string;
  height?: number;
  /** Accessible label; omit only when an adjacent element already states the value */
  label?: string;
}

const trackCss = css({
  flex: 1,
  background: colors.backgroundDark,
  borderRadius: radius.full,
  overflow: 'hidden',
});

const fillCss = css({
  height: '100%',
  borderRadius: radius.full,
  transition: `width ${transitions.base}`,
});

export const ProgressBar = ({ percentage, color, height = 6, label }: ProgressBarProps) => {
  const clamped = Math.max(0, Math.min(100, percentage));

  return (
    <div
      css={trackCss}
      style={{ height }}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      {...(label ? { 'aria-label': label } : {})}
    >
      <div
        css={fillCss}
        style={{ width: `${clamped}%`, background: color ?? colors.primary }}
      />
    </div>
  );
};
