/**
 * Status selector: a radio group of the five question statuses.
 */

import { css } from '@emotion/react';
import { STATUS_DEFINITIONS } from '@/core/status';
import { colors, fontSizes, radius, spacing, statusColors, transitions } from '@/styles/theme';
import type { QuestionStatus } from '@/types/waf';

export interface StatusSelectorProps {
  value: QuestionStatus;
  onChange: (status: QuestionStatus) => void;
}

const groupCss = css({
  display: 'flex',
  flexWrap: 'wrap',
  gap: spacing.xs,
});

const buttonCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  padding: '8px 14px',
  background: colors.background,
  border: `2px solid ${colors.border}`,
  borderRadius: radius.full,
  fontSize: fontSizes.sm,
  fontWeight: 500,
  color: colors.textLight,
  transition: `all ${transitions.fast}`,

  '&:hover': {
    borderColor: colors.textLight,
    color: colors.text,
  },
});

const dotCss = css({
  width: '10px',
  height: '10px',
  borderRadius: radius.full,
  flexShrink: 0,
});

export const StatusSelector = ({ value, onChange }: StatusSelectorProps) => {
  return (
    <div css={groupCss} role="radiogroup" aria-label="Status">
      {STATUS_DEFINITIONS.map((definition) => {
        const isSelected = definition.value === value;
        const accent = statusColors[definition.value];

        return (
          <button
            key={definition.value}
            type="button"
            role="radio"
            aria-checked={isSelected}
            css={buttonCss}
            style={
              isSelected
                ? { borderColor: accent, color: accent, background: `${accent}14`, fontWeight: 600 }
                : undefined
            }
            onClick={() => onChange(definition.value)}
          >
            <span css={dotCss} style={{ background: accent }} aria-hidden="true" />
            {definition.label}
          </button>
        );
      })}
    </div>
  );
};
