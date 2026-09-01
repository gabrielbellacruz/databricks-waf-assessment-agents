/**
 * Customer-facing WAF assessment report, laid out for print / Save-as-PDF.
 *
 * Rendered into a portal on `document.body` (a sibling of the app's `#root`) so
 * the print rules in GlobalStyles can hide the interactive app and print only
 * this document, keeping normal page flow so long reports paginate cleanly.
 * On mount it triggers the browser print dialog and calls `onDone` once the
 * dialog closes.
 */

import { css } from '@emotion/react';
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { BAND_LABEL, BAND_MIN, scoreBand } from '@/core/bands';
import { formatCloudProvider } from '@/core/report';
import type { ReportSummary } from '@/core/report';
import { getStatusLabel } from '@/core/status';
import { ProgressBar } from '@/components/ui/ProgressBar';
import {
  bandColors,
  colors,
  fontSizes,
  radius,
  severityColors,
  spacing,
  statusColors,
  withAlpha,
} from '@/styles/theme';
import type { Assessment, BacklogSeverity, BacklogTask } from '@/types/waf';
import type { AssessmentResults } from '@/types/results';
import { ScoreGauge } from './ScoreGauge';

export interface AssessmentReportProps {
  assessment: Assessment;
  results: AssessmentResults;
  summary: ReportSummary;
  /** Prioritized backlog to include, when one has been generated. */
  backlogTasks?: BacklogTask[];
  /** Called once the print dialog closes (printed or cancelled) */
  onDone: () => void;
}

function titleCase(value: BacklogSeverity): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString();
}

const rootCss = css({
  fontFamily: 'inherit',
  color: colors.text,
  background: colors.background,
  fontSize: fontSizes.sm,
  lineHeight: 1.5,
});

const coverCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.lg,
  minHeight: '92vh',
  breakAfter: 'page',
});

const eyebrowCss = css({
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  fontSize: fontSizes.sm,
  fontWeight: 700,
  color: colors.primaryText,
});

const reportTitleCss = css({
  fontSize: fontSizes['4xl'],
  color: colors.secondary,
});

const assessmentNameCss = css({
  fontSize: fontSizes['2xl'],
});

const descriptionCss = css({
  marginTop: spacing.xs,
  color: colors.textLight,
});

const coverScoreCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.md,
  padding: spacing.md,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
});

const coverScoreValueCss = css({
  fontSize: fontSizes['3xl'],
  fontWeight: 700,
  color: colors.secondary,
  fontVariantNumeric: 'tabular-nums',
});

const coverScoreLabelCss = css({
  fontSize: fontSizes.sm,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: colors.textLight,
});

const coverScoreCaptionCss = css({
  marginTop: '4px',
  color: colors.textLight,
});

const metaGridCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
  gap: spacing.sm,
  margin: 0,
});

const metaLabelCss = css({
  fontSize: fontSizes.xs,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: colors.textLight,
});

const metaValueCss = css({
  margin: 0,
  fontWeight: 600,
});

const sectionCss = css({
  breakBefore: 'page',
  paddingTop: spacing.sm,
});

const sectionTitleCss = css({
  fontSize: fontSizes['2xl'],
  color: colors.secondary,
  borderBottom: `2px solid ${colors.border}`,
  paddingBottom: spacing.xs,
  marginBottom: spacing.md,
});

const subheadCss = css({
  fontSize: fontSizes.lg,
  marginBottom: spacing.xs,
});

const paragraphCss = css({
  marginBottom: spacing.md,
});

const mutedCss = css({
  color: colors.textLight,
});

const twoColCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
  gap: spacing.md,
  breakInside: 'avoid',
});

const rankListCss = css({
  margin: `${spacing.xs} 0 0`,
  paddingLeft: '1.1rem',
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
});

const rankScoreCss = css({
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
});

const kpiRowCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
  gap: spacing.sm,
  marginBottom: spacing.lg,
});

const kpiCss = css({
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.md,
  padding: spacing.sm,
  breakInside: 'avoid',
});

const kpiValueCss = css({
  fontSize: fontSizes['2xl'],
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
});

const kpiLabelCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const matrixCss = css({
  borderCollapse: 'separate',
  borderSpacing: '3px',
  width: '100%',
  tableLayout: 'fixed',
});

const matrixCornerCss = css({
  width: '22%',
});

const matrixColHeaderCss = css({
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  padding: '5px 4px',
  borderRadius: radius.sm,
  textAlign: 'center',
});

const matrixRowHeaderCss = css({
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  padding: '5px 8px',
  borderRadius: radius.sm,
  textAlign: 'left',
});

const matrixCellCss = css({
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'center',
  padding: '8px 4px',
  borderRadius: radius.sm,
});

const legendCss = css({
  display: 'flex',
  gap: spacing.md,
  flexWrap: 'wrap',
  marginTop: spacing.sm,
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const legendItemCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
});

const swatchCss = css({
  width: '14px',
  height: '14px',
  borderRadius: radius.sm,
});

const layerBlockCss = css({
  marginBottom: spacing.md,
  breakInside: 'avoid',
});

const layerHeaderCss = css({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: spacing.sm,
});

const layerTitleCss = css({
  fontSize: fontSizes.lg,
});

const layerScoreCss = css({
  fontSize: fontSizes.xl,
  fontWeight: 700,
  color: colors.secondary,
  fontVariantNumeric: 'tabular-nums',
});

const layerMetaCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
  marginBottom: spacing.xs,
});

const pillarRowCss = css({
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) 3rem',
  alignItems: 'center',
  columnGap: spacing.sm,
  padding: '5px 0',
});

const pillarNameCss = css({
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

const pillarPctCss = css({
  textAlign: 'right',
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
});

const detailLayerTitleCss = css({
  fontSize: fontSizes.xl,
  color: colors.secondary,
  marginTop: spacing.md,
  marginBottom: spacing.xs,
});

const detailPillarCss = css({
  marginBottom: spacing.md,
  breakInside: 'avoid',
});

const detailPillarHeadCss = css({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: spacing.sm,
  marginBottom: '4px',
});

const qTableCss = css({
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: fontSizes.xs,
});

const qHeadCss = css({
  textAlign: 'left',
  fontWeight: 700,
  color: colors.textLight,
  borderBottom: `1px solid ${colors.border}`,
  padding: '4px 6px',
});

const qCellCss = css({
  verticalAlign: 'top',
  borderBottom: `1px solid ${colors.borderLight}`,
  padding: '4px 6px',
});

const qIdCss = css({
  fontVariantNumeric: 'tabular-nums',
  whiteSpace: 'nowrap',
  color: colors.textLight,
});

const qStatusCss = css({
  whiteSpace: 'nowrap',
  fontWeight: 700,
});

const backlogTaskCss = css({
  marginBottom: spacing.sm,
  paddingBottom: spacing.sm,
  borderBottom: `1px solid ${colors.borderLight}`,
  breakInside: 'avoid',
});

const backlogTaskHeadCss = css({
  display: 'flex',
  alignItems: 'baseline',
  gap: spacing.xs,
  marginBottom: '4px',
});

const backlogPriorityCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minWidth: '22px',
  height: '22px',
  padding: '0 6px',
  flexShrink: 0,
  borderRadius: radius.full,
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
});

const backlogTitleCss = css({
  fontSize: fontSizes.base,
});

const backlogDescCss = css({
  fontSize: fontSizes.sm,
  marginBottom: '6px',
});

const backlogBadgeRowCss = css({
  display: 'flex',
  gap: '6px',
  flexWrap: 'wrap',
  alignItems: 'center',
});

const backlogBadgeCss = css({
  padding: '2px 8px',
  borderRadius: radius.full,
  fontSize: fontSizes.xs,
  fontWeight: 600,
});

const backlogTagCss = css({
  padding: '2px 8px',
  borderRadius: radius.full,
  background: colors.backgroundDark,
  color: colors.textLight,
  fontSize: fontSizes.xs,
});

const backlogDependsCss = css({
  marginTop: '4px',
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const footerCss = css({
  marginTop: spacing.lg,
  paddingTop: spacing.sm,
  borderTop: `1px solid ${colors.borderLight}`,
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

export const AssessmentReport = ({
  assessment,
  results,
  summary,
  backlogTasks,
  onDone,
}: AssessmentReportProps) => {
  useEffect(() => {
    const handleAfterPrint = () => onDone();
    window.addEventListener('afterprint', handleAfterPrint);

    // Two frames so the report has painted before the print dialog opens
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => window.print());
    });

    return () => {
      window.removeEventListener('afterprint', handleAfterPrint);
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [onDone]);

  const { overall, categoryResults } = results;
  const layerNames = categoryResults.map((category) => category.name);
  const generatedOn = new Date().toLocaleDateString();
  const firstCategory = categoryResults[0];

  const kpis: { value: string | number; label: string }[] = [
    { value: `${overall.scorePercentage}%`, label: 'Overall score' },
    { value: `${overall.completionPercentage}%`, label: 'Completion' },
    {
      value: `${overall.answeredQuestions}/${overall.totalQuestions}`,
      label: 'Questions answered',
    },
    { value: overall.statusBreakdown.completed, label: 'Completed' },
    { value: overall.statusBreakdown.inProgress, label: 'In progress' },
    { value: overall.statusBreakdown.open, label: 'Open' },
  ];

  const report = (
    <div className="print-report-root">
      <div css={rootCss}>
        {/* Cover */}
        <section css={coverCss}>
          <div>
            <p css={eyebrowCss}>Databricks Well-Architected Framework</p>
            <h1 css={reportTitleCss}>Assessment Report</h1>
          </div>

          <div>
            <h2 css={assessmentNameCss}>{assessment.name}</h2>
            {assessment.description && <p css={descriptionCss}>{assessment.description}</p>}
          </div>

          <div css={coverScoreCss}>
            <ScoreGauge
              percentage={overall.scorePercentage}
              size={140}
              label={`Overall score: ${overall.scorePercentage}%`}
            />
            <div>
              <p css={coverScoreLabelCss}>Overall WAF Score</p>
              <p css={coverScoreValueCss}>{overall.scorePercentage}%</p>
              <p css={coverScoreCaptionCss}>
                {overall.totalScore}/{overall.maxPossibleScore} points · {overall.completionPercentage}%
                complete
              </p>
            </div>
          </div>

          <dl css={metaGridCss}>
            <div>
              <dt css={metaLabelCss}>Cloud provider</dt>
              <dd css={metaValueCss}>{formatCloudProvider(assessment.cloudProvider)}</dd>
            </div>
            <div>
              <dt css={metaLabelCss}>Architecture layers</dt>
              <dd css={metaValueCss}>{layerNames.length > 0 ? layerNames.join(', ') : '—'}</dd>
            </div>
            <div>
              <dt css={metaLabelCss}>Created</dt>
              <dd css={metaValueCss}>{formatDate(assessment.createdAt)}</dd>
            </div>
            <div>
              <dt css={metaLabelCss}>Last updated</dt>
              <dd css={metaValueCss}>{formatDate(assessment.updatedAt)}</dd>
            </div>
            <div>
              <dt css={metaLabelCss}>Report generated</dt>
              <dd css={metaValueCss}>{generatedOn}</dd>
            </div>
          </dl>
        </section>

        {/* Executive summary */}
        <section css={sectionCss}>
          <h2 css={sectionTitleCss}>Executive summary</h2>
          <p css={paragraphCss}>
            This report covers {layerNames.length}{' '}
            {layerNames.length === 1 ? 'architecture layer' : 'architecture layers'} across the seven
            Well-Architected pillars. {overall.answeredQuestions} of {overall.totalQuestions} questions
            have been answered ({overall.completionPercentage}% complete), for an overall score of{' '}
            {overall.scorePercentage}% ({overall.totalScore} of {overall.maxPossibleScore} points).
          </p>

          {summary.hasAnswers ? (
            <div css={twoColCss}>
              <div>
                <h3 css={subheadCss}>Strongest areas</h3>
                <ul css={rankListCss}>
                  {summary.strongest.map((cell) => (
                    <li key={`${cell.categoryName}-${cell.pillarName}`}>
                      {cell.pillarName} — {cell.categoryName}:{' '}
                      <span css={rankScoreCss}>{cell.scorePercentage}%</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 css={subheadCss}>Priority areas</h3>
                <ul css={rankListCss}>
                  {summary.priorities.map((cell) => (
                    <li key={`${cell.categoryName}-${cell.pillarName}`}>
                      {cell.pillarName} — {cell.categoryName}:{' '}
                      <span css={rankScoreCss}>{cell.scorePercentage}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p css={mutedCss}>No questions have been answered yet.</p>
          )}
        </section>

        {/* Score overview */}
        <section css={sectionCss}>
          <h2 css={sectionTitleCss}>Score overview</h2>

          <div css={kpiRowCss}>
            {kpis.map((kpi) => (
              <div key={kpi.label} css={kpiCss}>
                <div css={kpiValueCss}>{kpi.value}</div>
                <div css={kpiLabelCss}>{kpi.label}</div>
              </div>
            ))}
          </div>

          {firstCategory && (
            <>
              <h3 css={subheadCss}>Pillars across architecture layers</h3>
              <table css={matrixCss}>
                <thead>
                  <tr>
                    <th css={matrixCornerCss} scope="col" aria-label="Pillar" />
                    {categoryResults.map((category) => (
                      <th key={category.id} css={matrixColHeaderCss} scope="col">
                        {category.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {firstCategory.pillars.map((row) => (
                    <tr key={row.pillarIndex}>
                      <th css={matrixRowHeaderCss} scope="row">
                        {row.name}
                      </th>
                      {categoryResults.map((category) => {
                        const pillar = category.pillars[row.pillarIndex];
                        if (!pillar) return <td key={category.id} />;
                        const band = scoreBand(pillar.scorePercentage);
                        return (
                          <td
                            key={category.id}
                            css={matrixCellCss}
                            style={{ background: bandColors[band] }}
                          >
                            {pillar.scorePercentage}%
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>

              <div css={legendCss}>
                {(['met', 'partial', 'not-met'] as const).map((band) => (
                  <span key={band} css={legendItemCss}>
                    <span css={swatchCss} style={{ background: bandColors[band] }} aria-hidden="true" />
                    {BAND_LABEL[band]}
                  </span>
                ))}
                <span>
                  Met {BAND_MIN.met}–100% · Partially met {BAND_MIN.partial}–{BAND_MIN.met - 1}% · Not
                  met 0–{BAND_MIN.partial - 1}%
                </span>
              </div>
            </>
          )}
        </section>

        {/* Results by layer */}
        <section css={sectionCss}>
          <h2 css={sectionTitleCss}>Results by architecture layer</h2>
          {categoryResults.map((category) => (
            <div key={category.id} css={layerBlockCss}>
              <div css={layerHeaderCss}>
                <h3 css={layerTitleCss}>{category.name}</h3>
                <span css={layerScoreCss}>{category.scorePercentage}%</span>
              </div>
              <p css={layerMetaCss}>
                {category.answeredQuestions}/{category.totalQuestions} answered · {category.score}/
                {category.maxScore} points
              </p>
              <div>
                {category.pillars.map((pillar) => (
                  <div key={pillar.id} css={pillarRowCss}>
                    <span css={pillarNameCss}>{pillar.name}</span>
                    <span css={pillarPctCss}>{pillar.scorePercentage}%</span>
                    <div css={{ gridColumn: '1 / -1', marginTop: '2px' }}>
                      <ProgressBar
                        percentage={pillar.scorePercentage}
                        color={bandColors[scoreBand(pillar.scorePercentage)]}
                        label={`${pillar.name}: ${pillar.scorePercentage}%`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </section>

        {/* Implementation backlog */}
        {backlogTasks && backlogTasks.length > 0 && (
          <section css={sectionCss}>
            <h2 css={sectionTitleCss}>Implementation backlog</h2>
            {[...backlogTasks]
              .sort((a, b) => a.priority - b.priority)
              .map((task) => (
                <div key={`${task.priority}-${task.title}`} css={backlogTaskCss}>
                  <div css={backlogTaskHeadCss}>
                    <span css={backlogPriorityCss}>{task.priority}</span>
                    <h3 css={backlogTitleCss}>{task.title}</h3>
                  </div>
                  {task.description && <p css={backlogDescCss}>{task.description}</p>}
                  <div css={backlogBadgeRowCss}>
                    <span
                      css={backlogBadgeCss}
                      style={{
                        background: withAlpha(severityColors[task.criticality], 0.12),
                        color: severityColors[task.criticality],
                      }}
                    >
                      Criticality: {titleCase(task.criticality)}
                    </span>
                    <span
                      css={backlogBadgeCss}
                      style={{
                        background: withAlpha(severityColors[task.complexity], 0.12),
                        color: severityColors[task.complexity],
                      }}
                    >
                      Complexity: {titleCase(task.complexity)}
                    </span>
                    {task.timeline && <span css={backlogTagCss}>⏱ {task.timeline}</span>}
                    {task.pillar && <span css={backlogTagCss}>{task.pillar}</span>}
                    {task.layer && <span css={backlogTagCss}>{task.layer}</span>}
                  </div>
                  {task.dependsOn.length > 0 && (
                    <p css={backlogDependsCss}>Depends on: {task.dependsOn.join(', ')}</p>
                  )}
                </div>
              ))}
          </section>
        )}

        {/* Detailed responses */}
        <section css={sectionCss}>
          <h2 css={sectionTitleCss}>Detailed responses</h2>
          {categoryResults.map((category) => (
            <div key={category.id}>
              <h3 css={detailLayerTitleCss}>{category.name}</h3>
              {category.pillars.map((pillar) => (
                <div key={pillar.id} css={detailPillarCss}>
                  <div css={detailPillarHeadCss}>
                    <h4 css={subheadCss}>{pillar.name}</h4>
                    <span css={pillarPctCss}>{pillar.scorePercentage}%</span>
                  </div>
                  <table css={qTableCss}>
                    <thead>
                      <tr>
                        <th css={qHeadCss} scope="col">
                          ID
                        </th>
                        <th css={qHeadCss} scope="col">
                          Question
                        </th>
                        <th css={qHeadCss} scope="col">
                          Status
                        </th>
                        <th css={qHeadCss} scope="col">
                          Notes
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {pillar.questions.map((question) => {
                        const note =
                          assessment.notes?.[category.id]?.[pillar.id]?.[question.id] ?? '';
                        return (
                          <tr key={question.id}>
                            <td css={[qCellCss, qIdCss]}>{question.identifier}</td>
                            <td css={qCellCss}>{question.title}</td>
                            <td
                              css={[qCellCss, qStatusCss]}
                              style={{ color: statusColors[question.status] }}
                            >
                              {getStatusLabel(question.status)}
                            </td>
                            <td css={[qCellCss, mutedCss]}>{note}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          ))}
        </section>

        <footer css={footerCss}>
          Generated by the Databricks Well-Architected Framework Assessment Tool on {generatedOn}.
        </footer>
      </div>
    </div>
  );

  return createPortal(report, document.body);
};
