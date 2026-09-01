/**
 * Question tag: a small status-coloured chip that navigates to a question.
 * Used by the assessment sidebar and the results analysis section.
 */

import { css } from '@emotion/react';
import { fontSizes, radius, statusColors, transitions } from '@/styles/theme';
import type { QuestionStatus } from '@/types/waf';

export interface QuestionTagProps {
  identifier: string;
  status: QuestionStatus;
  onClick: () => void;
  tabIndex?: number;
}

const tagCss = css({
  padding: '2px 6px',
  border: '1px solid transparent',
  borderRadius: radius.sm,
  fontSize: '0.6875rem',
  fontFamily: 'inherit',
  fontWeight: 600,
  lineHeight: 1.4,
  transition: `all ${transitions.fast}`,

  '&:hover': {
    filter: 'brightness(0.92)',
  },
});

export const QuestionTag = ({ identifier, status, onClick, tabIndex }: QuestionTagProps) => {
  const accent = statusColors[status];

  return (
    <button
      type="button"
      css={tagCss}
      style={{ color: accent, background: `${accent}1A`, borderColor: `${accent}55` }}
      onClick={(event) => {
        // The tag sits inside another clickable row
        event.stopPropagation();
        onClick();
      }}
      aria-label={`${identifier} (${status})`}
      {...(tabIndex === undefined ? {} : { tabIndex })}
    >
      {identifier}
    </button>
  );
};

/** Shared layout for a row of tags */
export const tagListCss = css({
  display: 'flex',
  flexWrap: 'wrap',
  gap: '4px',
  fontSize: fontSizes.xs,
});
