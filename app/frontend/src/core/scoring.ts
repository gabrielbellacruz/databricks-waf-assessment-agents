/**
 * Scoring and results aggregation.
 * Pure functions over an assessment plus its filtered categories.
 */

import type { Assessment, Category, Pillar, QuestionStatus } from '@/types/waf';
import type {
  AssessmentResults,
  CategoryPrincipleGroups,
  CategoryResult,
  PillarPrincipleGroups,
  PillarResult,
  PrincipleGroup,
  QuestionResult,
  StatusBreakdown,
  UnansweredQuestion,
} from '@/types/results';
import { DEFAULT_STATUS, MAX_QUESTION_SCORE, getStatusScore, isAnswered } from './status';

/** An empty set of status counters */
function emptyBreakdown(): StatusBreakdown {
  return { open: 0, inProgress: 0, completed: 0, ignore: 0, answerLater: 0 };
}

/** Map a status onto the breakdown field it increments */
const BREAKDOWN_FIELD: Record<QuestionStatus, keyof StatusBreakdown> = {
  'open': 'open',
  'in-progress': 'inProgress',
  'completed': 'completed',
  'ignore': 'ignore',
  'answer-later': 'answerLater',
};

/** Add every counter of `source` into `target` */
function mergeBreakdown(target: StatusBreakdown, source: StatusBreakdown): void {
  target.open += source.open;
  target.inProgress += source.inProgress;
  target.completed += source.completed;
  target.ignore += source.ignore;
  target.answerLater += source.answerLater;
}

/**
 * Percentage of a pillar's questions that have been answered
 */
export function calculatePillarProgress(
  pillar: Pillar,
  answers: Record<string, QuestionStatus> | undefined,
): number {
  if (pillar.questions.length === 0) return 0;

  const answered = pillar.questions.filter((question) => isAnswered(answers?.[question.id])).length;
  return Math.round((answered / pillar.questions.length) * 100);
}

/**
 * Percentage of a category's questions that have been answered
 */
export function calculateCategoryProgress(
  category: Category,
  answers: Record<string, Record<string, QuestionStatus>> | undefined,
): number {
  const total = category.pillars.reduce((sum, pillar) => sum + pillar.questions.length, 0);
  if (total === 0) return 0;

  const answered = category.pillars.reduce(
    (sum, pillar) =>
      sum + pillar.questions.filter((question) => isAnswered(answers?.[pillar.id]?.[question.id])).length,
    0,
  );
  return Math.round((answered / total) * 100);
}

function percentage(score: number, maxScore: number): number {
  return maxScore > 0 ? Math.round((score / maxScore) * 100) : 0;
}

/**
 * Build the results for an assessment over its filtered categories
 */
export function buildResults(assessment: Assessment, categories: Category[]): AssessmentResults {
  const overallBreakdown = emptyBreakdown();
  let totalQuestions = 0;
  let answeredQuestions = 0;
  let totalScore = 0;
  let maxPossibleScore = 0;

  const categoryResults: CategoryResult[] = categories.map((category, categoryIndex) => {
    const categoryAnswers = assessment.answers[category.id] ?? {};
    const categoryBreakdown = emptyBreakdown();
    let categoryScore = 0;
    let categoryMaxScore = 0;
    let categoryTotal = 0;
    let categoryAnswered = 0;

    const pillarResults: PillarResult[] = category.pillars.map((pillar, pillarIndex) => {
      const pillarAnswers = categoryAnswers[pillar.id] ?? {};
      const breakdown = emptyBreakdown();
      let pillarScore = 0;
      let pillarAnswered = 0;

      const questions: QuestionResult[] = pillar.questions.map((question, questionIndex) => {
        const status = pillarAnswers[question.id] ?? DEFAULT_STATUS;
        const score = getStatusScore(status);

        pillarScore += score;
        breakdown[BREAKDOWN_FIELD[status]] += 1;

        if (isAnswered(status)) pillarAnswered += 1;

        return {
          id: question.id,
          identifier: question.identifier,
          principle: question.principle,
          title: question.title,
          status,
          score,
          categoryIndex,
          pillarIndex,
          questionIndex,
        };
      });

      const maxScore = pillar.questions.length * MAX_QUESTION_SCORE;

      categoryScore += pillarScore;
      categoryMaxScore += maxScore;
      categoryTotal += pillar.questions.length;
      categoryAnswered += pillarAnswered;
      mergeBreakdown(categoryBreakdown, breakdown);

      return {
        id: pillar.id,
        name: pillar.name,
        description: pillar.description,
        pillarIndex,
        totalQuestions: pillar.questions.length,
        answeredQuestions: pillarAnswered,
        score: pillarScore,
        maxScore,
        scorePercentage: percentage(pillarScore, maxScore),
        statusBreakdown: breakdown,
        questions,
      };
    });

    totalQuestions += categoryTotal;
    answeredQuestions += categoryAnswered;
    totalScore += categoryScore;
    maxPossibleScore += categoryMaxScore;
    mergeBreakdown(overallBreakdown, categoryBreakdown);

    return {
      id: category.id,
      name: category.name,
      description: category.description,
      categoryIndex,
      totalQuestions: categoryTotal,
      answeredQuestions: categoryAnswered,
      score: categoryScore,
      maxScore: categoryMaxScore,
      scorePercentage: percentage(categoryScore, categoryMaxScore),
      statusBreakdown: categoryBreakdown,
      pillars: pillarResults,
    };
  });

  return {
    assessmentId: assessment.id,
    assessmentName: assessment.name,
    categories: assessment.categories,
    createdAt: assessment.createdAt,
    updatedAt: assessment.updatedAt,
    categoryResults,
    overall: {
      totalQuestions,
      answeredQuestions,
      completionPercentage: percentage(answeredQuestions, totalQuestions),
      totalScore,
      maxPossibleScore,
      scorePercentage: percentage(totalScore, maxPossibleScore),
      statusBreakdown: overallBreakdown,
    },
  };
}

/**
 * Group a pillar's questions by principle, principles ordered by score.
 */
function groupPillarByPrinciple(pillar: PillarResult): PillarPrincipleGroups {
  const groups = new Map<string, PrincipleGroup>();

  for (const question of pillar.questions) {
    let group = groups.get(question.principle);
    if (!group) {
      group = { principle: question.principle, score: 0, maxScore: 0, percentage: 0, questions: [] };
      groups.set(question.principle, group);
    }

    group.score += question.score;
    group.maxScore += MAX_QUESTION_SCORE;
    group.questions.push(question);
  }

  const principles = [...groups.values()].map((group) => ({
    ...group,
    percentage: percentage(group.score, group.maxScore),
    // Keep tag order consistent with the assessment view
    questions: [...group.questions].sort((a, b) => a.questionIndex - b.questionIndex),
  }));

  principles.sort((a, b) => b.percentage - a.percentage);

  return {
    categoryIndex: pillar.questions[0]?.categoryIndex ?? 0,
    pillarName: pillar.name,
    pillarIndex: pillar.pillarIndex,
    score: pillar.score,
    maxScore: pillar.maxScore,
    percentage: pillar.scorePercentage,
    principles,
  };
}

/**
 * Group each category's pillars, and each pillar by principle, for the analysis
 * section.
 */
export function groupResultsByCategory(results: AssessmentResults): CategoryPrincipleGroups[] {
  return results.categoryResults.map((category) => ({
    categoryName: category.name,
    categoryIndex: category.categoryIndex,
    score: category.score,
    maxScore: category.maxScore,
    percentage: category.scorePercentage,
    pillars: category.pillars.map(groupPillarByPrinciple),
  }));
}

/**
 * Every question that still needs an answer, with where to find it
 */
export function findUnansweredQuestions(
  assessment: Assessment,
  categories: Category[],
): UnansweredQuestion[] {
  const unanswered: UnansweredQuestion[] = [];

  categories.forEach((category, categoryIndex) => {
    const categoryAnswers = assessment.answers[category.id] ?? {};

    category.pillars.forEach((pillar, pillarIndex) => {
      const pillarAnswers = categoryAnswers[pillar.id] ?? {};

      pillar.questions.forEach((question, questionIndex) => {
        if (isAnswered(pillarAnswers[question.id])) return;

        unanswered.push({
          categoryName: category.name,
          categoryIndex,
          pillarName: pillar.name,
          pillarIndex,
          questionIndex,
          identifier: question.identifier,
          title: question.title,
        });
      });
    });
  });

  return unanswered;
}
