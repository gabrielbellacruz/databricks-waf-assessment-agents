/**
 * Derived data for the customer-facing PDF report.
 * Pure functions over the already-computed assessment results.
 */

import type { CloudProvider } from '@/types/waf';
import type { AssessmentResults } from '@/types/results';

/** A single pillar-within-layer cell, ranked for the executive summary */
export interface RankedPillar {
  categoryName: string;
  pillarName: string;
  scorePercentage: number;
  answeredQuestions: number;
  totalQuestions: number;
}

export interface ReportSummary {
  /** Highest-scoring answered pillars, best first */
  strongest: RankedPillar[];
  /** Lowest-scoring answered pillars, worst first (excludes any in `strongest`) */
  priorities: RankedPillar[];
  /** Whether any question has been answered at all */
  hasAnswers: boolean;
}

/** Human-readable label for a cloud provider */
export function formatCloudProvider(provider: CloudProvider | null): string {
  switch (provider) {
    case 'aws':
      return 'AWS';
    case 'azure':
      return 'Azure';
    case 'gcp':
      return 'Google Cloud';
    default:
      return 'Not specified';
  }
}

/** Stable identity for a pillar-within-layer cell */
function cellKey(cell: RankedPillar): string {
  return `${cell.categoryName}::${cell.pillarName}`;
}

/**
 * Rank the assessment's pillar-within-layer cells into strongest areas and
 * priority areas. Only cells with at least one answered question are ranked, so
 * an untouched layer never reads as a strength or a gap.
 */
export function buildReportSummary(results: AssessmentResults, limit = 3): ReportSummary {
  const cells: RankedPillar[] = [];

  for (const category of results.categoryResults) {
    for (const pillar of category.pillars) {
      if (pillar.answeredQuestions === 0) continue;
      cells.push({
        categoryName: category.name,
        pillarName: pillar.name,
        scorePercentage: pillar.scorePercentage,
        answeredQuestions: pillar.answeredQuestions,
        totalQuestions: pillar.totalQuestions,
      });
    }
  }

  const strongest = [...cells]
    .sort((a, b) => b.scorePercentage - a.scorePercentage || a.pillarName.localeCompare(b.pillarName))
    .slice(0, limit);

  const strongestKeys = new Set(strongest.map(cellKey));

  const priorities = [...cells]
    .sort((a, b) => a.scorePercentage - b.scorePercentage || a.pillarName.localeCompare(b.pillarName))
    .filter((cell) => !strongestKeys.has(cellKey(cell)))
    .slice(0, limit);

  return { strongest, priorities, hasAnswers: cells.length > 0 };
}
