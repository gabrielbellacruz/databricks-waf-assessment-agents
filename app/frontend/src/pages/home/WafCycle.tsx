/**
 * The Well-Architected assessment cycle: a radial diagram of the five steps of
 * running WAF, arranged clockwise around a central hub.
 *
 * Drawn as a single SVG so the concentric rings, dots, dashed connectors and
 * labels scale together and the connectors stay aligned to their dots at any
 * width. The copy is fixed (the app is English-only), so label lines are laid
 * out with explicit coordinates rather than wrapped at render time.
 */

import { css } from '@emotion/react';
import { colors, fonts, spacing, withAlpha } from '@/styles/theme';

interface CycleStep {
  id: string;
  /** Dot on the outer ring. */
  dot: { x: number; y: number };
  /** Outer end of the dashed connector leading to the label. */
  connectorEnd: { x: number; y: number };
  /** x the label text is anchored to. */
  labelX: number;
  anchor: 'start' | 'middle' | 'end';
  /** When true the label sits below the connector (the bottom step). */
  below?: boolean;
  title: string;
  description: string[];
}

// Geometry is authored against this fixed viewBox; the SVG then scales to fit.
const CENTER = { x: 640, y: 340 };
const RING_RADIUS = 185;
const INNER_RADIUS = 150;

// Clockwise from the top-right, the five steps sit on the vertices of a regular
// pentagon (one vertex pointing down). Coordinates are precomputed from the
// pentagon angles so the file has no trig at render time.
const STEPS: readonly CycleStep[] = [
  {
    id: 'execute',
    dot: { x: 748.7, y: 190.3 },
    connectorEnd: { x: 848.7, y: 190.3 },
    labelX: 866.7,
    anchor: 'start',
    title: 'Execute, Assess & Review',
    description: [
      'Use the WAF Agents to evaluate the environment',
      'and your context. Review and assess with the',
      'responsible teams',
    ],
  },
  {
    id: 'prioritize',
    dot: { x: 815.9, y: 397.2 },
    connectorEnd: { x: 915.9, y: 397.2 },
    labelX: 933.9,
    anchor: 'start',
    title: 'Prioritize',
    description: ['Identify and prioritize high-risk issues'],
  },
  {
    id: 'remediate',
    dot: { x: 640, y: 525 },
    connectorEnd: { x: 640, y: 615 },
    labelX: 640,
    anchor: 'middle',
    below: true,
    title: 'Remediate',
    description: ['Take action to resolve identified issues and optimize'],
  },
  {
    id: 'educate',
    dot: { x: 464.1, y: 397.2 },
    connectorEnd: { x: 364.1, y: 397.2 },
    labelX: 346.1,
    anchor: 'end',
    title: 'Educate',
    description: ['Plan and provide training and resources for', 'your teams'],
  },
  {
    id: 'automate',
    dot: { x: 531.3, y: 190.3 },
    connectorEnd: { x: 431.3, y: 190.3 },
    labelX: 413.3,
    anchor: 'end',
    title: 'Automate, Monitor & Iterate',
    description: ['Continuously monitor the environment and iterate', 'improvements'],
  },
];

const ariaLabel =
  'The Well-Architected Framework assessment cycle, a continuous loop of five steps: ' +
  STEPS.map((step) => step.title).join('; ') +
  '.';

const cardCss = css({
  background: 'transparent',
  padding: `${spacing.lg} ${spacing.sm}`,
  overflow: 'hidden',
});

const svgCss = css({
  display: 'block',
  width: '100%',
  height: 'auto',
});

const titleTextCss = css({
  fontFamily: fonts.sans,
  fontSize: '24px',
  fontWeight: 700,
  fill: colors.text,
});

const descTextCss = css({
  fontFamily: fonts.sans,
  fontSize: '15.5px',
  fill: colors.textLight,
});

const centerTitleCss = css({
  fontFamily: fonts.sans,
  fontSize: '34px',
  fontWeight: 700,
  fill: colors.text,
});

const centerSubtitleCss = css({
  fontFamily: fonts.sans,
  fontSize: '30px',
  fontWeight: 600,
  fill: colors.primaryText,
});

export const WafCycle = () => (
  <div css={cardCss}>
    <svg
      css={svgCss}
      viewBox="0 0 1280 720"
      role="img"
      aria-label={ariaLabel}
      focusable="false"
    >
      {/* Faint outer band and the mint-ringed inner hub */}
      <circle
        cx={CENTER.x}
        cy={CENTER.y}
        r={RING_RADIUS}
        fill="none"
        stroke={colors.border}
        strokeWidth={18}
      />
      <circle
        cx={CENTER.x}
        cy={CENTER.y}
        r={INNER_RADIUS}
        fill={withAlpha(colors.background, 0.6)}
        stroke={colors.primary}
        strokeWidth={2.5}
      />

      <text x={CENTER.x} y={332} textAnchor="middle" css={centerTitleCss}>
        Well-Architected
      </text>
      <text x={CENTER.x} y={372} textAnchor="middle" css={centerSubtitleCss}>
        Framework
      </text>

      {STEPS.map((step) => {
        const titleY = step.below ? step.connectorEnd.y + 34 : step.connectorEnd.y - 24;
        const descStartY = step.below ? step.connectorEnd.y + 62 : step.connectorEnd.y + 6;
        return (
          <g key={step.id}>
            <line
              x1={step.dot.x}
              y1={step.dot.y}
              x2={step.connectorEnd.x}
              y2={step.connectorEnd.y}
              stroke={colors.primary}
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeDasharray="2 8"
            />
            <circle cx={step.dot.x} cy={step.dot.y} r={8} fill={colors.primary} />
            <text x={step.labelX} y={titleY} textAnchor={step.anchor} css={titleTextCss}>
              {step.title}
            </text>
            {step.description.map((line, index) => (
              <text
                key={line}
                x={step.labelX}
                y={descStartY + index * 20}
                textAnchor={step.anchor}
                css={descTextCss}
              >
                {line}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  </div>
);
