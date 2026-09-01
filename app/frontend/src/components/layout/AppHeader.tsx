/**
 * Application header: logo, current assessment chip, page nav, language picker.
 */

import { css } from '@emotion/react';
import { useCurrentAssessment } from '@/store/assessmentStore';
import { colors, fontSizes, layout, radius, spacing, transitions } from '@/styles/theme';
import type { PageName } from '@/types/navigation';

export interface AppHeaderProps {
  currentPage: PageName;
  onNavigate: (page: PageName) => void;
  onOpenAssessmentManager: () => void;
}

const NAV_ITEMS: readonly { page: PageName; label: string }[] = [
  { page: 'home', label: 'Home' },
  { page: 'assessment', label: 'Assessment' },
  { page: 'results', label: 'Results' },
];

const headerCss = css({
  position: 'sticky',
  top: 0,
  zIndex: 1020,
  minHeight: layout.headerHeight,
  background: colors.secondary,
  color: colors.textInverse,
});

const innerCss = css({
  maxWidth: layout.containerMaxWidth,
  margin: '0 auto',
  padding: `${spacing.xs} ${spacing.sm}`,
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  flexWrap: 'wrap',
});

const logoCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  marginRight: 'auto',

  img: {
    height: '64px',
    width: 'auto',
  },

  h1: {
    fontSize: fontSizes.lg,
    fontWeight: 600,
  },
});

const chipCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  padding: '4px 10px',
  borderRadius: radius.full,
  background: 'rgba(255, 255, 255, 0.12)',
  fontSize: fontSizes.xs,
});

const chipLabelCss = css({
  opacity: 0.75,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
});

const chipNameCss = css({
  fontWeight: 600,
  maxWidth: '18ch',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

const managerButtonCss = css({
  display: 'flex',
  alignItems: 'center',
  padding: '6px 8px',
  background: 'rgba(255, 255, 255, 0.12)',
  border: '1px solid rgba(255, 255, 255, 0.2)',
  borderRadius: radius.md,
  color: colors.textInverse,
  transition: `background ${transitions.fast}`,

  '&:hover': {
    background: 'rgba(255, 255, 255, 0.22)',
  },
});

const navCss = css({
  display: 'flex',
  gap: '4px',
});

const navButtonCss = css({
  padding: '6px 14px',
  background: 'transparent',
  border: 'none',
  borderRadius: radius.md,
  color: 'rgba(255, 255, 255, 0.8)',
  fontSize: fontSizes.sm,
  fontWeight: 500,
  transition: `all ${transitions.fast}`,

  '&:hover': {
    background: 'rgba(255, 255, 255, 0.12)',
    color: colors.textInverse,
  },

  '&[aria-current="page"]': {
    background: colors.primary,
    color: colors.textInverse,
    fontWeight: 600,
  },
});

export const AppHeader = ({
  currentPage,
  onNavigate,
  onOpenAssessmentManager,
}: AppHeaderProps) => {
  const assessment = useCurrentAssessment();

  return (
    <header css={headerCss}>
      <div css={innerCss}>
        <div css={logoCss}>
          <img src={`${import.meta.env.BASE_URL}assets/icons/logo-waf.svg`} alt="" />
          <h1>WAF Assessment Tool</h1>
        </div>

        <div css={chipCss}>
          {assessment ? (
            <>
              <span css={chipLabelCss}>Assessment:</span>
              <span css={chipNameCss}>{assessment.name}</span>
            </>
          ) : (
            <span css={chipLabelCss}>No assessment selected</span>
          )}
        </div>

        <button
          type="button"
          css={managerButtonCss}
          onClick={onOpenAssessmentManager}
          aria-label="Assessment Manager"
        >
          <span aria-hidden="true">📋</span>
        </button>

        <nav css={navCss} aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.page}
              type="button"
              css={navButtonCss}
              aria-current={currentPage === item.page ? 'page' : undefined}
              onClick={() => onNavigate(item.page)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
};
