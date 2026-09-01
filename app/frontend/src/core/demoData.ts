/**
 * Demo data generation.
 * Fills an assessment with plausible random answers for demonstrations.
 */

import type { AssessmentAnswers, Category, QuestionStatus } from '@/types/waf';

/**
 * Status distribution. Each range is drawn at random, then the four
 * probabilities are normalized to sum to 100%.
 */
const DISTRIBUTION: readonly { status: QuestionStatus; min: number; max: number }[] = [
  { status: 'open', min: 5, max: 20 },
  { status: 'in-progress', min: 15, max: 30 },
  { status: 'completed', min: 60, max: 80 },
  { status: 'ignore', min: 0, max: 5 },
];

/**
 * Build a status picker from freshly drawn, normalized probabilities
 */
function createStatusPicker(): () => QuestionStatus {
  const drawn = DISTRIBUTION.map(({ status, min, max }) => ({
    status,
    weight: min + Math.random() * (max - min),
  }));

  const total = drawn.reduce((sum, entry) => sum + entry.weight, 0);
  const normalized = drawn.map((entry) => ({
    status: entry.status,
    probability: (entry.weight / total) * 100,
  }));

  return () => {
    const roll = Math.random() * 100;
    let cumulative = 0;

    for (const entry of normalized) {
      cumulative += entry.probability;
      if (roll < cumulative) return entry.status;
    }

    // Rounding can leave the roll just past the last boundary
    return 'completed';
  };
}

/**
 * Generate random answers covering every question in the given categories
 */
export function generateDemoAnswers(categories: Category[]): AssessmentAnswers {
  const pickStatus = createStatusPicker();
  const answers: AssessmentAnswers = {};

  for (const category of categories) {
    const categoryAnswers: Record<string, Record<string, QuestionStatus>> = {};
    for (const pillar of category.pillars) {
      const pillarAnswers: Record<string, QuestionStatus> = {};
      for (const question of pillar.questions) {
        pillarAnswers[question.id] = pickStatus();
      }
      categoryAnswers[pillar.id] = pillarAnswers;
    }
    answers[category.id] = categoryAnswers;
  }

  return answers;
}
