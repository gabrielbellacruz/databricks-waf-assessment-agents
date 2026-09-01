/**
 * Modal dialog.
 *
 * Renders into a portal, closes on Escape and on backdrop click, and restores
 * focus to the element that opened it.
 */

import { css } from '@emotion/react';
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';
import { colors, fontSizes, radius, shadows, spacing, withAlpha, zIndex } from '@/styles/theme';

export type ModalSize = 'sm' | 'md' | 'lg';

export interface ModalProps {
  title: string;
  onClose: () => void;
  size?: ModalSize;
  children: ReactNode;
}

const MAX_WIDTHS: Record<ModalSize, string> = {
  sm: '440px',
  md: '640px',
  lg: '860px',
};

const overlayCss = css({
  position: 'fixed',
  inset: 0,
  zIndex: zIndex.modal,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: spacing.sm,
  background: withAlpha(colors.secondary, 0.55),
  backdropFilter: 'blur(2px)',
});

const dialogCss = css({
  width: '100%',
  maxHeight: '90vh',
  display: 'flex',
  flexDirection: 'column',
  background: colors.background,
  borderRadius: radius.lg,
  boxShadow: shadows.xl,
  overflow: 'hidden',
});

const headerCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.sm,
  padding: `${spacing.sm} ${spacing.md}`,
  borderBottom: `1px solid ${colors.borderLight}`,
});

const titleCss = css({
  fontSize: fontSizes.xl,
});

const closeCss = css({
  background: 'none',
  border: 'none',
  fontSize: fontSizes['2xl'],
  lineHeight: 1,
  color: colors.textLight,
  padding: spacing.xs,
  borderRadius: radius.sm,

  '&:hover': {
    color: colors.primaryText,
    background: colors.backgroundLight,
  },
});

const bodyCss = css({
  padding: spacing.md,
  overflowY: 'auto',
});

export const Modal = ({ title, onClose, size = 'md', children }: ModalProps) => {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previouslyFocused = document.activeElement;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', handleKeyDown);

    // Move focus into the dialog so screen readers announce it
    dialogRef.current?.focus();

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [onClose]);

  return createPortal(
    <div
      css={overlayCss}
      onClick={(event) => {
        // Only a click on the backdrop itself closes the dialog
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        css={dialogCss}
        style={{ maxWidth: MAX_WIDTHS[size] }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div css={headerCss}>
          <h2 css={titleCss}>{title}</h2>
          <button type="button" css={closeCss} onClick={onClose} aria-label="Close dialog">
            ×
          </button>
        </div>
        <div css={bodyCss}>{children}</div>
      </div>
    </div>,
    document.body,
  );
};
