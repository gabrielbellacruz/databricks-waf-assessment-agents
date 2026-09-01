/**
 * Navigation sidebar: a three-level accordion of categories, each listing its
 * WAF pillars, and the active pillar listing its principles with the status
 * tags of their questions. Only the active category and pillar are expanded.
 */

import { css } from '@emotion/react';
import { getPillarPrinciples, getQuestionsForPrinciple } from '@/core/pillars';
import { calculateCategoryProgress, calculatePillarProgress } from '@/core/scoring';
import { DEFAULT_STATUS } from '@/core/status';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { colors, fontSizes, radius, spacing, transitions } from '@/styles/theme';
import type { AssessmentAnswers, Category } from '@/types/waf';
import type { QuestionPosition } from '@/types/navigation';
import { QuestionTag, tagListCss } from './QuestionTag';

export interface PillarsSidebarProps {
  categories: Category[];
  answers: AssessmentAnswers;
  position: QuestionPosition;
  onNavigate: (position: QuestionPosition) => void;
}

const sidebarCss = css({
  alignSelf: 'start',
  position: 'sticky',
  top: `calc(${spacing.sm} + 56px)`,
  maxHeight: 'calc(100vh - 96px)',
  overflowY: 'auto',
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  padding: spacing.xs,
});

const headingCss = css({
  padding: `${spacing.xs} ${spacing.xs} 0`,
  fontSize: fontSizes.xs,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: colors.textLight,
});

const categoryButtonCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  width: '100%',
  padding: spacing.xs,
  background: 'none',
  border: 'none',
  borderRadius: radius.md,
  textAlign: 'left',
  transition: `background ${transitions.fast}`,

  '&:hover': {
    background: colors.backgroundLight,
  },
});

const activeCategoryCss = css({
  background: `${colors.primary}0F`,
});

const categoryNameCss = css({
  flex: 1,
  fontSize: fontSizes.sm,
  fontWeight: 700,
  color: colors.text,
});

const pillarButtonCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  width: '100%',
  padding: `4px ${spacing.xs}`,
  background: 'none',
  border: 'none',
  borderRadius: radius.md,
  textAlign: 'left',
  transition: `background ${transitions.fast}`,

  '&:hover': {
    background: colors.backgroundLight,
  },
});

const activePillarCss = css({
  background: `${colors.primary}0A`,
});

const pillarNumberCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '22px',
  height: '22px',
  flexShrink: 0,
  borderRadius: radius.full,
  background: colors.backgroundDark,
  color: colors.textLight,
  fontSize: '0.6875rem',
  fontWeight: 700,
});

const pillarNameCss = css({
  flex: 1,
  fontSize: fontSizes.sm,
  fontWeight: 600,
  color: colors.text,
});

const percentCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
  fontVariantNumeric: 'tabular-nums',
});

const categoryPanelCss = css({
  padding: `${spacing.xs} 0 ${spacing.xs} ${spacing.xs}`,
  display: 'flex',
  flexDirection: 'column',
  gap: '2px',
});

const panelCss = css({
  padding: `${spacing.xs} ${spacing.xs} ${spacing.xs} ${spacing.sm}`,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.xs,
});

/**
 * The principle row holds the name button and the question tags as siblings -
 * nesting the tags inside the name button would be invalid HTML.
 */
const principleRowCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  padding: '6px 8px',
  border: `1px solid transparent`,
  borderRadius: radius.sm,

  '&:hover': {
    background: colors.backgroundLight,
  },
});

const activePrincipleCss = css({
  borderColor: `${colors.primary}55`,
  background: `${colors.primary}0A`,
});

const principleNameCss = css({
  width: '100%',
  padding: 0,
  background: 'none',
  border: 'none',
  textAlign: 'left',
  fontSize: fontSizes.xs,
  fontWeight: 500,
  color: colors.textLight,

  '&:hover': {
    color: colors.text,
  },
});

export const PillarsSidebar = ({
  categories,
  answers,
  position,
  onNavigate,
}: PillarsSidebarProps) => {
  const activeCategory = categories[position.categoryIndex];
  const activePillar = activeCategory?.pillars[position.pillarIndex];
  const activePrinciple = activePillar?.questions[position.questionIndex]?.principle ?? null;

  return (
    <aside css={sidebarCss} aria-label="Architecture layers">
      <h2 css={headingCss}>Architecture Layers</h2>

      {categories.map((category, categoryIndex) => {
        const isCategoryActive = categoryIndex === position.categoryIndex;
        const categoryAnswers = answers[category.id];
        const categoryProgress = calculateCategoryProgress(category, categoryAnswers);

        return (
          <div key={category.id}>
            <button
              type="button"
              css={[categoryButtonCss, isCategoryActive && activeCategoryCss]}
              aria-expanded={isCategoryActive}
              aria-current={isCategoryActive ? 'true' : undefined}
              onClick={() => onNavigate({ categoryIndex, pillarIndex: 0, questionIndex: 0 })}
            >
              <span css={categoryNameCss}>{category.name}</span>
              <span css={percentCss}>{categoryProgress}%</span>
            </button>

            <div style={{ padding: `0 ${spacing.xs}` }}>
              <ProgressBar
                percentage={categoryProgress}
                height={4}
                label={`${category.name}: ${categoryProgress}%`}
              />
            </div>

            {isCategoryActive && (
              <div css={categoryPanelCss}>
                {category.pillars.map((pillar, pillarIndex) => {
                  const isPillarActive = pillarIndex === position.pillarIndex;
                  const pillarAnswers = categoryAnswers?.[pillar.id];
                  const pillarProgress = calculatePillarProgress(pillar, pillarAnswers);

                  return (
                    <div key={pillar.id}>
                      <button
                        type="button"
                        css={[pillarButtonCss, isPillarActive && activePillarCss]}
                        aria-expanded={isPillarActive}
                        onClick={() => onNavigate({ categoryIndex, pillarIndex, questionIndex: 0 })}
                      >
                        <span css={pillarNumberCss} aria-hidden="true">
                          {pillarIndex + 1}
                        </span>
                        <span css={pillarNameCss}>{pillar.name}</span>
                        <span css={percentCss}>{pillarProgress}%</span>
                      </button>

                      {isPillarActive && (
                        <div css={panelCss}>
                          {getPillarPrinciples(pillar).map((principle) => {
                            const questions = getQuestionsForPrinciple(pillar, principle);
                            const isPrincipleActive = activePrinciple === principle;
                            const firstIndex = questions[0]?.questionIndex ?? 0;

                            return (
                              <div
                                key={principle}
                                css={[principleRowCss, isPrincipleActive && activePrincipleCss]}
                              >
                                <button
                                  type="button"
                                  css={principleNameCss}
                                  onClick={() =>
                                    onNavigate({ categoryIndex, pillarIndex, questionIndex: firstIndex })
                                  }
                                >
                                  {principle}
                                </button>
                                <div css={tagListCss}>
                                  {questions.map(({ question, questionIndex }) => (
                                    <QuestionTag
                                      key={question.id}
                                      identifier={question.identifier}
                                      status={pillarAnswers?.[question.id] ?? DEFAULT_STATUS}
                                      onClick={() =>
                                        onNavigate({ categoryIndex, pillarIndex, questionIndex })
                                      }
                                    />
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
};
