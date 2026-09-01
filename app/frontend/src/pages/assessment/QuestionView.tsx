/**
 * Question view: the current question, its badges, and the status selector.
 */

import { css } from '@emotion/react';
import { extractCloudProviders } from '@/core/pillars';
import { colors, fontSizes, radius, spacing } from '@/styles/theme';
import type {
  AgentFinding,
  AgentRun,
  Category,
  CloudProvider,
  Pillar,
  Question,
  QuestionStatus,
} from '@/types/waf';
import { AgentPanel } from './AgentPanel';
import { GuidancePanel } from './GuidancePanel';
import { QuestionNotes } from './QuestionNotes';
import { StatusSelector } from './StatusSelector';

export interface QuestionViewProps {
  category: Category;
  pillar: Pillar;
  question: Question;
  status: QuestionStatus;
  /** The free-text note for this question, or an empty string when none. */
  note: string;
  cloudProvider: CloudProvider | null;
  onStatusChange: (status: QuestionStatus) => void;
  onNoteChange: (note: string) => void;
  onEditAssessment: () => void;
  /** Agent's proposed verdict for this question, when a run has produced one. */
  agentFinding?: AgentFinding;
  /** Latest agent run for this layer, for the analyzing / failed / rerun states. */
  agentRun?: AgentRun | null;
  /** Re-trigger the agent for this layer. */
  onRerunAgent: () => void;
}

const breadcrumbCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: fontSizes.xs,
  color: colors.textLight,
  marginBottom: spacing.xs,
});

const headerRowCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  flexWrap: 'wrap',
  marginBottom: spacing.xs,
});

const identifierCss = css({
  padding: '2px 8px',
  borderRadius: radius.sm,
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  fontFamily: 'inherit',
});

const principleCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
  fontWeight: 500,
});

const badgeCss = css({
  padding: '2px 8px',
  borderRadius: radius.full,
  background: colors.backgroundDark,
  color: colors.textLight,
  fontSize: '0.6875rem',
  fontWeight: 600,
});

const titleCss = css({
  fontSize: fontSizes['2xl'],
  marginBottom: spacing.sm,
});

const detailsCss = css({
  padding: spacing.sm,
  background: colors.backgroundLight,
  borderRadius: radius.md,
  fontSize: fontSizes.sm,
  color: colors.textLight,
  whiteSpace: 'pre-wrap',
  marginBottom: spacing.md,
});

const statusRowCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.xs,
});

const statusLabelCss = css({
  fontSize: fontSizes.sm,
  fontWeight: 600,
});

const requiredCss = css({
  color: colors.error,
});

export const QuestionView = ({
  category,
  pillar,
  question,
  status,
  note,
  cloudProvider,
  onStatusChange,
  onNoteChange,
  onEditAssessment,
  agentFinding,
  agentRun = null,
  onRerunAgent,
}: QuestionViewProps) => {
  const cloudProviders = extractCloudProviders(question.details);

  return (
    <article>
      <nav css={breadcrumbCss} aria-label="Breadcrumb">
        <span>{category.name}</span>
        <span aria-hidden="true">›</span>
        <span>{pillar.name}</span>
        <span aria-hidden="true">›</span>
        <span>{question.identifier}</span>
      </nav>

      <div css={headerRowCss}>
        <span css={identifierCss}>{question.identifier}</span>
        <span css={principleCss}>{question.principle}</span>
        <span css={{ marginLeft: 'auto', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {cloudProviders.map((provider) => (
            <span key={provider} css={badgeCss}>
              {provider}
            </span>
          ))}
        </span>
      </div>

      <h2 css={titleCss}>{question.title}</h2>

      <div css={detailsCss}>{question.details ?? 'No details available'}</div>

      <div css={statusRowCss}>
        <span css={statusLabelCss}>
          Status: <span css={requiredCss}>*</span>
        </span>
        <StatusSelector value={status} onChange={onStatusChange} />
      </div>

      <QuestionNotes key={question.id} note={note} onChange={onNoteChange} />

      <AgentPanel finding={agentFinding} run={agentRun} onRerun={onRerunAgent} />

      {question.databricksGuidance && (
        <GuidancePanel
          guidance={question.databricksGuidance}
          cloudProvider={cloudProvider}
          onEditAssessment={onEditAssessment}
        />
      )}
    </article>
  );
};
