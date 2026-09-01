/**
 * Results page: overall score, KPIs, radar chart, per-category summaries, and
 * the pillar/principle-level analysis grouped by category.
 */

import { css } from '@emotion/react';
import { useCallback, useMemo, useState } from 'react';
import { buildResults, groupResultsByCategory } from '@/core/scoring';
import { buildReportSummary } from '@/core/report';
import { buildBacklogContext } from '@/core/backlogContext';
import { downloadAssessment } from '@/core/assessmentFile';
import { useBacklog } from '@/hooks/useBacklog';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { colors, fontSizes, layout, radius, spacing, statusColors } from '@/styles/theme';
import type { Assessment, Category } from '@/types/waf';
import type { QuestionPosition } from '@/types/navigation';
import { AssessmentReport } from './AssessmentReport';
import { BacklogPanel } from './BacklogPanel';
import { PillarAnalysis, pillarAnchorId, pillarKey } from './PillarAnalysis';
import { ScoreGauge } from './ScoreGauge';
import { ScoreMatrix } from './ScoreMatrix';

export interface ResultsPageProps {
  assessment: Assessment | null;
  categories: Category[];
  onOpenAssessmentManager: () => void;
  onContinueAssessment: () => void;
  onNavigateToQuestion: (position: QuestionPosition) => void;
}

const containerCss = css({
  maxWidth: layout.containerMaxWidth,
  margin: '0 auto',
  padding: `${spacing.md} ${spacing.sm}`,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.lg,
});

const headerCss = css({
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: spacing.md,
  flexWrap: 'wrap',
  padding: spacing.md,
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
});

const titleCss = css({
  fontSize: fontSizes['2xl'],
  marginBottom: '4px',
});

const metadataCss = css({
  display: 'flex',
  gap: spacing.sm,
  flexWrap: 'wrap',
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const scoreBoxCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
});

const scoreHeadingCss = css({
  fontSize: fontSizes.base,
  fontWeight: 700,
});

const scoreCaptionCss = css({
  marginTop: '6px',
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

const sectionTitleCss = css({
  fontSize: fontSizes.xl,
  marginBottom: spacing.sm,
});

// A section header that collapses its body, like the per-layer category toggles.
const sectionToggleCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  width: '100%',
  padding: 0,
  marginBottom: spacing.sm,
  background: 'none',
  border: 'none',
  textAlign: 'left',
  cursor: 'pointer',
});

const sectionToggleTitleCss = css({
  fontSize: fontSizes.xl,
});

const backlogCountCss = css({
  marginLeft: 'auto',
  fontSize: fontSizes.sm,
  color: colors.textLight,
  fontVariantNumeric: 'tabular-nums',
});

const categorySectionCss = css({
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  padding: spacing.md,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.md,
});

const categoryHeaderCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.sm,
  flexWrap: 'wrap',
  width: '100%',
  padding: 0,
  background: 'none',
  border: 'none',
  textAlign: 'left',
  cursor: 'pointer',
});

const categoryTitleGroupCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  minWidth: 0,
});

const chevronCss = css({
  fontSize: fontSizes.sm,
  color: colors.textLight,
  flexShrink: 0,
});

const categoryScoreCss = css({
  fontSize: fontSizes['2xl'],
  fontWeight: 700,
  color: colors.secondary,
  fontVariantNumeric: 'tabular-nums',
});

const subTitleCss = css({
  fontSize: fontSizes.base,
  marginBottom: spacing.xs,
  color: colors.textLight,
});

const kpiRowCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
  gap: spacing.sm,
});

const kpiCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
});

const kpiValueCss = css({
  fontSize: fontSizes['2xl'],
  fontWeight: 700,
  lineHeight: 1.1,
  fontVariantNumeric: 'tabular-nums',
});

const kpiLabelCss = css({
  fontSize: fontSizes.sm,
  fontWeight: 600,
});

const kpiSubLabelCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const pillarsGridCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  gap: spacing.sm,
});

const pillarCardHeaderCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  marginBottom: spacing.xs,
});

const pillarNumberCss = css({
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

const pillarCardBodyCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
});

const statusBadgeListCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  fontSize: fontSizes.xs,
  flex: 1,
});

const statusBadgeCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.xs,
  padding: '2px 8px',
  borderRadius: radius.sm,
});

const categoriesCss = css({
  display: 'flex',
  gap: '4px',
  flexWrap: 'wrap',
  marginTop: spacing.xs,
});

const categoryTagCss = css({
  padding: '2px 8px',
  borderRadius: radius.full,
  background: colors.backgroundDark,
  color: colors.textLight,
  fontSize: '0.6875rem',
});

const actionsCss = css({
  display: 'flex',
  gap: spacing.xs,
  justifyContent: 'flex-end',
  flexWrap: 'wrap',
});

const emptyStateCss = css({
  maxWidth: layout.containerMaxWidth,
  margin: '0 auto',
  padding: `${spacing['2xl']} ${spacing.sm}`,
  textAlign: 'center',
});

export const ResultsPage = ({
  assessment,
  categories,
  onOpenAssessmentManager,
  onContinueAssessment,
  onNavigateToQuestion,
}: ResultsPageProps) => {
  const [expandedPillar, setExpandedPillar] = useState<string | null>(null);
  const [isPrinting, setIsPrinting] = useState(false);
  const [backlogCollapsed, setBacklogCollapsed] = useState(false);
  const stopPrinting = useCallback(() => setIsPrinting(false), []);
  // Every layer starts collapsed; the user expands the ones they want to inspect.
  const [collapsedCategories, setCollapsedCategories] = useState<ReadonlySet<string>>(
    () => new Set(categories.map((category) => category.id)),
  );

  const toggleCategory = (id: string) =>
    setCollapsedCategories((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });

  const results = useMemo(
    () => (assessment ? buildResults(assessment, categories) : null),
    [assessment, categories],
  );
  const groups = useMemo(() => (results ? groupResultsByCategory(results) : []), [results]);
  const reportSummary = useMemo(() => (results ? buildReportSummary(results) : null), [results]);

  const backlog = useBacklog(assessment?.id ?? null);
  const generateBacklogRun = backlog.generate;
  const generateBacklog = useCallback(() => {
    if (!assessment || !results) return;
    void generateBacklogRun(buildBacklogContext(results, assessment));
  }, [assessment, results, generateBacklogRun]);

  if (!assessment || !results) {
    return (
      <div css={emptyStateCss}>
        <h2>No Assessment Selected</h2>
        <p css={{ color: colors.textLight, marginBottom: spacing.md }}>
          Please select or create an assessment to view results.
        </p>
        <Button variant="primary" onClick={onOpenAssessmentManager}>
          Select Assessment
        </Button>
      </div>
    );
  }

  const { overall } = results;

  const kpis = [
    {
      icon: '🎯',
      color: colors.text,
      value: `${overall.scorePercentage}%`,
      label: 'Overall Score',
      sublabel: `${overall.totalScore}/${overall.maxPossibleScore} points`,
    },
    {
      icon: '✓',
      color: colors.text,
      value: `${overall.completionPercentage}%`,
      label: 'Completion Rate',
      sublabel: `${overall.answeredQuestions}/${overall.totalQuestions} questions`,
    },
    {
      icon: '⚡',
      color: colors.text,
      value: overall.statusBreakdown.inProgress,
      label: 'In Progress',
      sublabel: `${overall.statusBreakdown.completed} completed`,
    },
    {
      icon: '📋',
      color: colors.text,
      value: overall.statusBreakdown.open,
      label: 'Open Items',
      sublabel: `${overall.statusBreakdown.ignore} ignored`,
    },
  ];

  const handleExpandPillar = (categoryIndex: number, pillarIndex: number) => {
    setExpandedPillar(pillarKey(categoryIndex, pillarIndex));
    document
      .getElementById(pillarAnchorId(categoryIndex, pillarIndex))
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div css={containerCss}>
      <header css={headerCss}>
        <div>
          <h1 css={titleCss}>
            Assessment Results: {results.assessmentName}
          </h1>
          <div css={metadataCss}>
            <span>
              📅 Created: {new Date(results.createdAt).toLocaleDateString()}
            </span>
            <span>
              🔄 Updated: {new Date(results.updatedAt).toLocaleDateString()}
            </span>
          </div>
          {results.categories.length > 0 && (
            <div css={categoriesCss}>
              {results.categories.map((category) => (
                <span key={category} css={categoryTagCss}>
                  {category}
                </span>
              ))}
            </div>
          )}
        </div>

        <div css={scoreBoxCss}>
          <ScoreGauge
            percentage={overall.scorePercentage}
            size={110}
            label={`Overall score: ${overall.scorePercentage}%`}
          />
          <div>
            <p css={scoreHeadingCss}>Overall WAF Score</p>
            <p css={scoreCaptionCss}>
              {overall.totalScore}/{overall.maxPossibleScore} points
            </p>
          </div>
        </div>
      </header>

      <section>
        <h2 css={sectionTitleCss}>Overall Progress</h2>
        <div css={kpiRowCss}>
          {kpis.map((kpi) => (
            <Card key={kpi.label}>
              <div css={kpiCss}>
                <span aria-hidden="true" css={{ fontSize: fontSizes.xl }}>
                  {kpi.icon}
                </span>
                <div>
                  <div css={kpiValueCss} style={{ color: kpi.color }}>
                    {kpi.value}
                  </div>
                  <div css={kpiLabelCss}>{kpi.label}</div>
                  <div css={kpiSubLabelCss}>{kpi.sublabel}</div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 css={sectionTitleCss}>Score Matrix</h2>
        <Card>
          <h3 css={{ fontSize: fontSizes.base, marginBottom: spacing.sm }}>
            Pillars across architecture layers
          </h3>
          <ScoreMatrix
            categories={results.categoryResults}
            onNavigateToQuestion={onNavigateToQuestion}
          />
        </Card>
      </section>

      <section>
        <h2 css={sectionTitleCss}>Results by Architecture Layers</h2>
        <div css={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
          {results.categoryResults.map((category) => {
            const categoryGroup = groups[category.categoryIndex];
            const isCollapsed = collapsedCategories.has(category.id);
            const bodyId = `category-body-${category.id}`;

            return (
              <div key={category.id} css={categorySectionCss}>
                <button
                  type="button"
                  css={categoryHeaderCss}
                  aria-expanded={!isCollapsed}
                  aria-controls={bodyId}
                  onClick={() => toggleCategory(category.id)}
                >
                  <span css={categoryTitleGroupCss}>
                    <span css={chevronCss} aria-hidden="true">
                      {isCollapsed ? '▸' : '▾'}
                    </span>
                    <span css={{ minWidth: 0 }}>
                      <h3 css={{ fontSize: fontSizes.lg }}>{category.name}</h3>
                      <span css={kpiSubLabelCss}>
                        {category.answeredQuestions}/{category.totalQuestions} answered ·{' '}
                        {category.pillars.length} pillars
                      </span>
                    </span>
                  </span>
                  <span css={categoryScoreCss}>{category.scorePercentage}%</span>
                </button>

                {!isCollapsed && (
                  <div id={bodyId} css={{ display: 'flex', flexDirection: 'column', gap: spacing.md }}>
                    <div>
                      <h4 css={subTitleCss}>Score by Pillar</h4>
                      <div css={pillarsGridCss}>
                        {category.pillars.map((pillar) => {
                          const answeredPercentage =
                            pillar.totalQuestions > 0
                              ? Math.round((pillar.answeredQuestions / pillar.totalQuestions) * 100)
                              : 0;

                          return (
                            <Card
                              key={pillar.id}
                              interactive
                              role="button"
                              tabIndex={0}
                              aria-label={`${pillar.name}: ${pillar.scorePercentage}%`}
                              onClick={() => handleExpandPillar(category.categoryIndex, pillar.pillarIndex)}
                              onKeyDown={(event) => {
                                if (event.key !== 'Enter' && event.key !== ' ') return;
                                event.preventDefault();
                                handleExpandPillar(category.categoryIndex, pillar.pillarIndex);
                              }}
                            >
                              <div css={pillarCardHeaderCss}>
                                <span css={pillarNumberCss} aria-hidden="true">
                                  {pillar.pillarIndex + 1}
                                </span>
                                <div css={{ minWidth: 0 }}>
                                  <h3 css={{ fontSize: fontSizes.base }}>{pillar.name}</h3>
                                  <span css={kpiSubLabelCss}>
                                    {pillar.answeredQuestions}/{pillar.totalQuestions} answered (
                                    {answeredPercentage}%)
                                  </span>
                                </div>
                              </div>

                              <div css={pillarCardBodyCss}>
                                <ScoreGauge
                                  percentage={pillar.scorePercentage}
                                  size={110}
                                  label={`${pillar.name}: ${pillar.scorePercentage}%`}
                                />
                                <div css={statusBadgeListCss}>
                                  {(
                                    [
                                      ['open', pillar.statusBreakdown.open, 'Open'],
                                      ['in-progress', pillar.statusBreakdown.inProgress, 'In Progress'],
                                      ['completed', pillar.statusBreakdown.completed, 'Completed'],
                                      ['ignore', pillar.statusBreakdown.ignore, 'Ignore'],
                                    ] as const
                                  ).map(([status, count, label]) => (
                                    <span
                                      key={status}
                                      css={statusBadgeCss}
                                      style={{
                                        background: `${statusColors[status]}1A`,
                                        color: statusColors[status],
                                      }}
                                    >
                                      <span>{label}</span>
                                      <strong>{count}</strong>
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </Card>
                          );
                        })}
                      </div>
                    </div>

                    {categoryGroup && (
                      <div>
                        <h4 css={subTitleCss}>Analysis by Pillar &amp; Principle</h4>
                        <PillarAnalysis
                          categoryIndex={category.categoryIndex}
                          pillars={categoryGroup.pillars}
                          expandedKey={expandedPillar}
                          onToggle={(key) =>
                            setExpandedPillar((current) => (current === key ? null : key))
                          }
                          onNavigateToQuestion={onNavigateToQuestion}
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <button
          type="button"
          css={sectionToggleCss}
          aria-expanded={!backlogCollapsed}
          aria-controls="backlog-body"
          onClick={() => setBacklogCollapsed((collapsed) => !collapsed)}
        >
          <span css={chevronCss} aria-hidden="true">
            {backlogCollapsed ? '▸' : '▾'}
          </span>
          <h2 css={sectionToggleTitleCss}>Implementation Backlog</h2>
          {backlog.tasks.length > 0 && (
            <span css={backlogCountCss}>
              {backlog.tasks.length} {backlog.tasks.length === 1 ? 'task' : 'tasks'}
            </span>
          )}
        </button>
        {!backlogCollapsed && (
          <div id="backlog-body">
            <BacklogPanel
              run={backlog.run}
              tasks={backlog.tasks}
              onGenerate={generateBacklog}
              enabled={backlog.enabled}
            />
          </div>
        )}
      </section>

      <div css={actionsCss}>
        <Button variant="primary" onClick={() => setIsPrinting(true)}>
          Export PDF Report
        </Button>
        <Button variant="secondary" onClick={() => downloadAssessment(assessment)}>
          Export Assessment Data
        </Button>
        <Button variant="secondary" onClick={onContinueAssessment}>
          Continue Assessment
        </Button>
      </div>

      {isPrinting && reportSummary && (
        <AssessmentReport
          assessment={assessment}
          results={results}
          summary={reportSummary}
          backlogTasks={backlog.tasks}
          onDone={stopPrinting}
        />
      )}
    </div>
  );
};
