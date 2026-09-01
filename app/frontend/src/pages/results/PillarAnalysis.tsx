/**
 * Analysis by pillar, within one category: each pillar broken down by
 * principle. Single-open accordion across the whole page, controlled by the
 * parent so the cards above can expand a specific entry.
 */

import { css } from '@emotion/react';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { colors, fontSizes, radius, spacing } from '@/styles/theme';
import type { PillarPrincipleGroups } from '@/types/results';
import type { QuestionPosition } from '@/types/navigation';
import { QuestionTag, tagListCss } from '@/pages/assessment/QuestionTag';

export interface PillarAnalysisProps {
  categoryIndex: number;
  pillars: PillarPrincipleGroups[];
  /** Key of the expanded pillar (`categoryIndex-pillarIndex`), or null */
  expandedKey: string | null;
  onToggle: (key: string) => void;
  onNavigateToQuestion: (position: QuestionPosition) => void;
}

/** Stable key for a pillar across the whole page */
export function pillarKey(categoryIndex: number, pillarIndex: number): string {
  return `${categoryIndex}-${pillarIndex}`;
}

/** DOM id of a pillar's analysis card, for scroll-into-view */
export function pillarAnchorId(categoryIndex: number, pillarIndex: number): string {
  return `pillar-analysis-${categoryIndex}-${pillarIndex}`;
}

const listCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.xs,
});

const cardCss = css({
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  overflow: 'hidden',
});

const headerCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  width: '100%',
  padding: spacing.sm,
  background: 'none',
  border: 'none',
  textAlign: 'left',

  '&:hover': {
    background: colors.backgroundLight,
  },
});

const numberCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '26px',
  height: '26px',
  flexShrink: 0,
  borderRadius: radius.full,
  // Darker Lava, so the white numeral stays legible
  background: colors.primary,
  color: colors.textOnPrimary,
  fontSize: fontSizes.xs,
  fontWeight: 700,
});

const nameCss = css({
  fontSize: fontSizes.base,
});

const summaryCss = css({
  display: 'flex',
  gap: spacing.xs,
  fontSize: fontSizes.xs,
  color: colors.textLight,
  flexWrap: 'wrap',
});

const scoreCss = css({
  fontWeight: 700,
  color: colors.primaryText,
  fontVariantNumeric: 'tabular-nums',
});

const panelCss = css({
  padding: `0 ${spacing.sm} ${spacing.sm}`,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.sm,
});

const principleCss = css({
  padding: spacing.xs,
  background: colors.backgroundLight,
  borderRadius: radius.md,
});

const principleHeaderCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.xs,
  marginBottom: '6px',
  fontSize: fontSizes.sm,
});

const metaCss = css({
  display: 'flex',
  justifyContent: 'space-between',
  gap: spacing.xs,
  marginTop: '4px',
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

export const PillarAnalysis = ({
  categoryIndex,
  pillars,
  expandedKey,
  onToggle,
  onNavigateToQuestion,
}: PillarAnalysisProps) => {
  return (
    <div css={listCss}>
      {pillars.map((group) => {
        const key = pillarKey(categoryIndex, group.pillarIndex);
        const isExpanded = expandedKey === key;
        const panelId = `${pillarAnchorId(categoryIndex, group.pillarIndex)}-panel`;

        return (
          <div key={key} css={cardCss} id={pillarAnchorId(categoryIndex, group.pillarIndex)}>
            <button
              type="button"
              css={headerCss}
              aria-expanded={isExpanded}
              aria-controls={panelId}
              onClick={() => onToggle(key)}
            >
              <span css={numberCss} aria-hidden="true">
                {group.pillarIndex + 1}
              </span>
              <span css={{ flex: 1, minWidth: 0 }}>
                <h4 css={nameCss}>{group.pillarName}</h4>
                <span css={summaryCss}>
                  <span css={scoreCss}>{group.percentage}%</span>
                  <span>
                    {group.score}/{group.maxScore} points
                  </span>
                  <span>
                    {group.principles.length}{' '}
                    {group.principles.length === 1 ? 'item' : 'items'}
                  </span>
                </span>
              </span>
              <span aria-hidden="true">{isExpanded ? '▴' : '▾'}</span>
            </button>

            {isExpanded && (
              <div css={panelCss} id={panelId}>
                {group.principles.map((principle) => (
                  <div key={principle.principle} css={principleCss}>
                    <div css={principleHeaderCss}>
                      <span>{principle.principle}</span>
                      <span css={scoreCss}>{principle.percentage}%</span>
                    </div>
                    <ProgressBar
                      percentage={principle.percentage}
                      label={`${principle.principle}: ${principle.percentage}%`}
                    />
                    <div css={metaCss}>
                      <span>
                        {principle.score}/{principle.maxScore} points
                      </span>
                      <span>
                        {principle.questions.length}{' '}
                        {principle.questions.length === 1 ? 'question' : 'questions'}
                      </span>
                    </div>
                    <div css={tagListCss} style={{ marginTop: '6px' }}>
                      {principle.questions.map((question) => (
                        <QuestionTag
                          key={question.id}
                          identifier={question.identifier}
                          status={question.status}
                          onClick={() =>
                            onNavigateToQuestion({
                              categoryIndex: question.categoryIndex,
                              pillarIndex: question.pillarIndex,
                              questionIndex: question.questionIndex,
                            })
                          }
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
