/**
 * Implementation backlog panel on the Results page: triggers the results-level
 * backlog agent and renders its prioritized tasks. Read-only; the agent runs in
 * the backend and this polls via useBacklog in the parent.
 */

import { css } from '@emotion/react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { colors, fontSizes, radius, severityColors, spacing, withAlpha } from '@/styles/theme';
import type { BacklogRun, BacklogSeverity, BacklogTask } from '@/types/waf';

export interface BacklogPanelProps {
  run: BacklogRun | null;
  tasks: BacklogTask[];
  /** Trigger a (re)generation of the backlog. */
  onGenerate: () => void;
  /** False when the backend can't run the agent (local dev). */
  enabled?: boolean;
}

const introCss = css({
  color: colors.textLight,
  marginBottom: spacing.sm,
  maxWidth: '60ch',
});

const headerCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.sm,
  flexWrap: 'wrap',
  marginBottom: spacing.sm,
});

const mutedCss = css({
  color: colors.textLight,
});

const errorCss = css({
  color: colors.error,
  marginBottom: spacing.sm,
});

const listCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.sm,
});

const taskHeaderCss = css({
  display: 'flex',
  alignItems: 'baseline',
  gap: spacing.xs,
  marginBottom: '4px',
});

const priorityCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  minWidth: '24px',
  height: '24px',
  padding: '0 6px',
  flexShrink: 0,
  borderRadius: radius.full,
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
});

const taskTitleCss = css({
  fontSize: fontSizes.base,
});

const taskDescCss = css({
  fontSize: fontSizes.sm,
  color: colors.text,
  marginBottom: spacing.xs,
});

const badgeRowCss = css({
  display: 'flex',
  gap: '6px',
  flexWrap: 'wrap',
  alignItems: 'center',
});

const badgeCss = css({
  padding: '2px 8px',
  borderRadius: radius.full,
  fontSize: fontSizes.xs,
  fontWeight: 600,
});

const tagCss = css({
  padding: '2px 8px',
  borderRadius: radius.full,
  background: colors.backgroundDark,
  color: colors.textLight,
  fontSize: fontSizes.xs,
});

const dependsCss = css({
  marginTop: spacing.xs,
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const captionCss = css({
  marginTop: spacing.sm,
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

export interface SeverityBadgeProps {
  label: string;
  level: BacklogSeverity;
}

function SeverityBadge({ label, level }: SeverityBadgeProps) {
  const color = severityColors[level];
  return (
    <span css={badgeCss} style={{ background: withAlpha(color, 0.12), color }}>
      {label}: {level.charAt(0).toUpperCase() + level.slice(1)}
    </span>
  );
}

export const BacklogPanel = ({ run, tasks, onGenerate, enabled = true }: BacklogPanelProps) => {
  const status = run?.status ?? null;
  const generating = status === 'queued' || status === 'running';
  const failed = status === 'failed';
  const done = status === 'done';

  if (!enabled) {
    return (
      <Card>
        <p css={mutedCss}>
          The backlog agent runs in the deployed app (it needs workspace access to the model) and
          isn&apos;t available in local development.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <div css={headerCss}>
        <p css={introCss}>
          Generate a prioritized, actionable backlog from this assessment — each task ranked by
          criticality and complexity, with a timeline and dependencies.
        </p>
        <Button variant="primary" onClick={onGenerate} disabled={generating}>
          {generating ? 'Generating…' : done || failed ? 'Regenerate' : 'Generate backlog'}
        </Button>
      </div>

      {generating && (
        <p css={mutedCss}>Analyzing the assessment and prioritizing tasks… this can take a minute.</p>
      )}

      {failed && (
        <p css={errorCss}>
          Backlog generation failed{run?.error ? `: ${run.error}` : '.'} You can try again.
        </p>
      )}

      {done && tasks.length === 0 && (
        <p css={mutedCss}>No backlog items — this assessment has no open gaps to plan for.</p>
      )}

      {tasks.length > 0 && (
        <>
          <div css={listCss}>
            {[...tasks]
              .sort((a, b) => a.priority - b.priority)
              .map((task) => (
                <div key={`${task.priority}-${task.title}`}>
                  <div css={taskHeaderCss}>
                    <span css={priorityCss} aria-label={`Priority ${task.priority}`}>
                      {task.priority}
                    </span>
                    <h4 css={taskTitleCss}>{task.title}</h4>
                  </div>
                  {task.description && <p css={taskDescCss}>{task.description}</p>}
                  <div css={badgeRowCss}>
                    <SeverityBadge label="Criticality" level={task.criticality} />
                    <SeverityBadge label="Complexity" level={task.complexity} />
                    {task.timeline && <span css={tagCss}>⏱ {task.timeline}</span>}
                    {task.pillar && <span css={tagCss}>{task.pillar}</span>}
                    {task.layer && <span css={tagCss}>{task.layer}</span>}
                  </div>
                  {task.dependsOn.length > 0 && (
                    <p css={dependsCss}>Depends on: {task.dependsOn.join(', ')}</p>
                  )}
                </div>
              ))}
          </div>
          {run?.finishedAt && (
            <p css={captionCss}>
              {tasks.length} {tasks.length === 1 ? 'task' : 'tasks'} · generated{' '}
              {new Date(run.finishedAt).toLocaleString()}
            </p>
          )}
        </>
      )}
    </Card>
  );
};
