/**
 * Score bands: how a 0-100 score percentage maps to a met/partial/not-met
 * rating. Single source of truth so the score matrix and the PDF report agree
 * on both the thresholds and the labels.
 */

export type ScoreBand = 'met' | 'partial' | 'not-met';

/** Lowest score percentage that still counts as each band */
export const BAND_MIN = { met: 67, partial: 34 } as const;

/** The band a score percentage falls into */
export function scoreBand(percentage: number): ScoreBand {
  if (percentage >= BAND_MIN.met) return 'met';
  if (percentage >= BAND_MIN.partial) return 'partial';
  return 'not-met';
}

/** Display label per band */
export const BAND_LABEL: Readonly<Record<ScoreBand, string>> = {
  'met': 'Met',
  'partial': 'Partially met',
  'not-met': 'Not met',
};
