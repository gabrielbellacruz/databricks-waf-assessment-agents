/**
 * Score matrix: a pillar × architecture-layer heatmap. Each cell is one
 * pillar's score within one layer, colored by how fully it is met.
 */

import { css } from '@emotion/react';
import { BAND_LABEL, BAND_MIN, scoreBand } from '@/core/bands';
import type { ScoreBand } from '@/core/bands';
import { bandColors, colors, fontSizes, radius, spacing } from '@/styles/theme';
import type { CategoryResult } from '@/types/results';
import type { QuestionPosition } from '@/types/navigation';

export interface ScoreMatrixProps {
  categories: CategoryResult[];
  onNavigateToQuestion: (position: QuestionPosition) => void;
}

/** Percentage range shown next to each band in the legend */
const BAND_RANGE: Record<ScoreBand, string> = {
  'met': `${BAND_MIN.met}–100%`,
  'partial': `${BAND_MIN.partial}–${BAND_MIN.met - 1}%`,
  'not-met': `0–${BAND_MIN.partial - 1}%`,
};

const scrollCss = css({
  overflowX: 'auto',
});

const ROW_HEADER_WIDTH = '200px';

const tableCss = css({
  borderCollapse: 'separate',
  borderSpacing: '4px',
  width: '100%',
  minWidth: '720px',
});

const cornerCss = css({
  background: 'transparent',
  width: ROW_HEADER_WIDTH,
});

const colHeaderCss = css({
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  padding: `${spacing.xs} 6px`,
  borderRadius: radius.sm,
  textAlign: 'center',
  verticalAlign: 'middle',
});

const rowHeaderCss = css({
  background: colors.secondary,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  padding: `${spacing.xs} ${spacing.sm}`,
  borderRadius: radius.sm,
  textAlign: 'left',
  width: ROW_HEADER_WIDTH,
  lineHeight: 1.25,
  overflowWrap: 'break-word',
});

const cellCss = css({
  padding: 0,
});

const cellButtonCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  minWidth: '64px',
  height: '52px',
  border: 'none',
  borderRadius: radius.sm,
  color: colors.textInverse,
  fontSize: fontSizes.xs,
  fontWeight: 700,
  fontVariantNumeric: 'tabular-nums',
  cursor: 'pointer',
  transition: 'filter 120ms ease, transform 120ms ease',

  '&:hover': {
    filter: 'brightness(1.08)',
  },

  '&:focus-visible': {
    outline: `2px solid ${colors.text}`,
    outlineOffset: '2px',
  },
});

const legendCss = css({
  display: 'flex',
  gap: spacing.md,
  flexWrap: 'wrap',
  marginTop: spacing.sm,
});

const legendItemCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const swatchCss = css({
  width: '18px',
  height: '18px',
  borderRadius: radius.sm,
  flexShrink: 0,
});

const legendRangeCss = css({
  fontVariantNumeric: 'tabular-nums',
  opacity: 0.8,
});

export const ScoreMatrix = ({ categories, onNavigateToQuestion }: ScoreMatrixProps) => {
  const firstCategory = categories[0];
  if (!firstCategory) return null;

  // Pillars are the same set, in the same order, in every category
  const pillarRows = firstCategory.pillars.map((pillar) => ({
    pillarIndex: pillar.pillarIndex,
    name: pillar.name,
  }));

  return (
    <div>
      <div css={scrollCss}>
        <table css={tableCss}>
          <thead>
            <tr>
              <th css={cornerCss} scope="col" aria-label="Pillar" />
              {categories.map((category) => (
                <th key={category.id} css={colHeaderCss} scope="col">
                  {category.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pillarRows.map((row) => (
              <tr key={row.pillarIndex}>
                <th css={rowHeaderCss} scope="row">
                  {row.name}
                </th>
                {categories.map((category) => {
                  const pillar = category.pillars[row.pillarIndex];
                  if (!pillar) {
                    return <td key={category.id} css={cellCss} />;
                  }

                  const band = scoreBand(pillar.scorePercentage);
                  const label = `${row.name} in ${category.name}: ${pillar.scorePercentage}% (${BAND_LABEL[band]})`;

                  return (
                    <td key={category.id} css={cellCss}>
                      <button
                        type="button"
                        css={cellButtonCss}
                        style={{ background: bandColors[band] }}
                        title={label}
                        aria-label={label}
                        onClick={() =>
                          onNavigateToQuestion({
                            categoryIndex: category.categoryIndex,
                            pillarIndex: row.pillarIndex,
                            questionIndex: 0,
                          })
                        }
                      >
                        {pillar.scorePercentage}%
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div css={legendCss}>
        {(['met', 'partial', 'not-met'] as const).map((band) => (
          <span key={band} css={legendItemCss}>
            <span css={swatchCss} style={{ background: bandColors[band] }} aria-hidden="true" />
            {BAND_LABEL[band]} <span css={legendRangeCss}>({BAND_RANGE[band]})</span>
          </span>
        ))}
      </div>
    </div>
  );
};
