/**
 * Button primitive.
 */

import { css } from '@emotion/react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { colors, fontSizes, radius, shadows, spacing, transitions } from '@/styles/theme';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

const baseCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: spacing.xs,
  border: '2px solid transparent',
  borderRadius: radius.md,
  fontWeight: 600,
  transition: `all ${transitions.fast}`,
  whiteSpace: 'nowrap',

  '&:disabled': {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
});

const sizeCss: Record<ButtonSize, ReturnType<typeof css>> = {
  sm: css({ padding: `6px 12px`, fontSize: fontSizes.sm }),
  md: css({ padding: `10px 20px`, fontSize: fontSizes.base }),
  lg: css({ padding: `14px 28px`, fontSize: fontSizes.lg }),
};

const variantCss: Record<ButtonVariant, ReturnType<typeof css>> = {
  primary: css({
    // The darker Lava, because white on Lava 600 is only 3.62:1 - this is 5.71:1
    background: colors.primary,
    color: colors.textOnPrimary,
    '&:hover:not(:disabled)': {
      // Darkens further on hover, so white stays legible
      background: colors.primary,
      boxShadow: shadows.glow,
      transform: 'translateY(-1px)',
    },
  }),
  secondary: css({
    background: colors.background,
    color: colors.text,
    borderColor: colors.border,
    '&:hover:not(:disabled)': {
      borderColor: colors.primary,
      color: colors.primaryText,
    },
  }),
  ghost: css({
    background: 'transparent',
    color: colors.textLight,
    '&:hover:not(:disabled)': {
      background: colors.backgroundDark,
      color: colors.text,
    },
  }),
  danger: css({
    background: 'transparent',
    color: colors.error,
    borderColor: 'transparent',
    '&:hover:not(:disabled)': {
      background: colors.errorLight,
    },
  }),
};

export const Button = ({
  variant = 'secondary',
  size = 'md',
  children,
  type = 'button',
  ...rest
}: ButtonProps) => (
  <button type={type} css={[baseCss, sizeCss[size], variantCss[variant]]} {...rest}>
    {children}
  </button>
);
