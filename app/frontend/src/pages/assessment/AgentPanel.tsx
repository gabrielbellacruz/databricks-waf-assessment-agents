/**
 * Agent panel: shows the ingestion agent's proposed verdict for the current
 * question, its rationale, and the evidence behind it (the literal query and a
 * summary) for explainability. Read-only in M1 - a reviewer still sets the workflow
 * status themselves.
 */

import { useState } from 'react';
import { css } from '@emotion/react';
import { getStatusLabel, VERDICT_STATUS } from '@/core/status';
import { colors, fontSizes, radius, spacing, statusColors } from '@/styles/theme';
import type { AgentFinding, AgentRun, AgentVerdict } from '@/types/waf';

export interface AgentPanelProps {
  finding: AgentFinding | undefined;
  /** Latest agent run for this layer, or null when none has run. */
  run: AgentRun | null;
  /** Re-trigger the agent for this layer (e.g. after a failure or a workspace change). */
  onRerun: () => void;
}

/**
 * How a verdict is shown, matching the WAF workflow-status classification and
 * its colours (met -> Completed, partial -> In Progress, not_met -> Open). A
 * verdict the agent could not determine (`unknown`) is surfaced as "Open" - a
 * gap for a reviewer to work through - rather than a separate review state.
 */
function verdictDisplay(verdict: AgentVerdict): { label: string; color: string } {
  const status = verdict === 'unknown' ? 'open' : VERDICT_STATUS[verdict];
  return { label: getStatusLabel(status), color: statusColors[status] };
}

const panelCss = css({
  marginTop: spacing.md,
  border: `1px solid ${colors.border}`,
  borderRadius: radius.md,
  overflow: 'hidden',
});

const headerCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  padding: `${spacing.xs} ${spacing.sm}`,
  background: colors.backgroundLight,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: colors.textLight,
});

const rerunButtonCss = css({
  marginLeft: 'auto',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  background: 'none',
  border: 'none',
  padding: 0,
  color: colors.primaryText,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  cursor: 'pointer',

  '&:hover': {
    textDecoration: 'underline',
  },
});

const errorCss = css({
  fontSize: fontSizes.sm,
  color: colors.error,
});

const bodyCss = css({
  padding: spacing.sm,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.xs,
});

const verdictRowCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  flexWrap: 'wrap',
});

const badgeCss = css({
  padding: '2px 10px',
  borderRadius: radius.full,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
});

const confidenceCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
  fontWeight: 600,
});

const rationaleCss = css({
  fontSize: fontSizes.sm,
  color: colors.text,
});

const sourcesButtonCss = css({
  alignSelf: 'flex-start',
  background: 'none',
  border: 'none',
  padding: 0,
  color: colors.info,
  fontSize: fontSizes.xs,
  fontWeight: 600,
  cursor: 'pointer',
  textDecoration: 'underline',
});

const evidenceCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
  background: colors.backgroundLight,
  borderRadius: radius.sm,
  padding: spacing.xs,
  whiteSpace: 'pre-wrap',
  fontFamily: 'monospace',
  overflowX: 'auto',
});

const mutedCss = css({
  fontSize: fontSizes.sm,
  color: colors.textLight,
  fontStyle: 'italic',
});

export const AgentPanel = ({ finding, run, onRerun }: AgentPanelProps) => {
  const [showSources, setShowSources] = useState(false);

  const status = run?.status ?? null;

  // Nothing to show if no agent has run for this layer at all.
  if (!finding && status === null) {
    return null;
  }

  const analyzing = status === 'queued' || status === 'running';
  const failed = status === 'failed';
  // A rerun makes sense once a run has settled - to retry a failure or to
  // re-evaluate against a changed workspace. It's a no-op while one is active.
  const canRerun = status === 'done' || status === 'failed';

  return (
    <section css={panelCss} aria-label="Agent analysis">
      <div css={headerCss}>
        <span>Agent analysis</span>
        {canRerun && (
          <button
            type="button"
            css={rerunButtonCss}
            onClick={onRerun}
            title="Re-run the agent for this layer"
          >
            <span aria-hidden="true">↻</span> Rerun agent
          </button>
        )}
      </div>
      <div css={bodyCss}>
        {analyzing && <p css={mutedCss}>The agent is analyzing this question…</p>}

        {failed && (
          <p css={errorCss}>
            The agent run failed{run?.error ? `: ${run.error}` : '.'} You can rerun it.
          </p>
        )}

        {finding && !finding.autoAssessable && (
          <p css={mutedCss}>{finding.rationale}</p>
        )}

        {finding && finding.autoAssessable && (
          <>
            <div css={verdictRowCss}>
              <span css={badgeCss} style={{ background: verdictDisplay(finding.verdict).color }}>
                {verdictDisplay(finding.verdict).label}
              </span>
              {finding.score !== null && (
                <span css={confidenceCss}>{Math.round(finding.score * 100)}%</span>
              )}
            </div>

            <p css={rationaleCss}>{finding.rationale}</p>

            {finding.sources.length > 0 && (
              <>
                <button
                  type="button"
                  css={sourcesButtonCss}
                  aria-expanded={showSources}
                  onClick={() => setShowSources((v) => !v)}
                >
                  {showSources ? 'Hide sources' : `Show sources (${finding.sources.length})`}
                </button>
                {showSources &&
                  finding.sources.map((evidence, i) => (
                    <div key={i} css={evidenceCss}>
                      <strong>{evidence.summary}</strong>
                      {evidence.detail && `\n\n${evidence.detail}`}
                      {evidence.ref && `\n\n${evidence.ref}`}
                    </div>
                  ))}
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
};
