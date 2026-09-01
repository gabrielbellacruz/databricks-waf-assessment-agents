/**
 * Card surface primitive.
 */

import { css } from '@emotion/react';
import type { HTMLAttributes, ReactNode } from 'react';
import { colors, radius, shadows, spacing, transitions } from '@/styles/theme';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Lift the card on hover; use for cards that act as links or buttons */
  interactive?: boolean;
  children: ReactNode;
}

const cardCss = css({
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  boxShadow: shadows.sm,
  padding: spacing.md,
});

const interactiveCss = css({
  cursor: 'pointer',
  transition: `transform ${transitions.fast}, box-shadow ${transitions.fast}, border-color ${transitions.fast}`,

  '&:hover': {
    transform: 'translateY(-2px)',
    boxShadow: shadows.md,
    borderColor: colors.primary,
  },
});

export const Card = ({ interactive = false, children, ...rest }: CardProps) => (
  <div css={[cardCss, interactive && interactiveCss]} {...rest}>
    {children}
  </div>
);
