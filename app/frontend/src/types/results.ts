/**
 * Result types produced by the scoring functions.
 */

import type { QuestionStatus } from './waf';

/** Count of questions per status */
export interface StatusBreakdown {
  open: number;
  inProgress: number;
  completed: number;
  ignore: number;
  answerLater: number;
}

export interface QuestionResult {
  id: string;
  identifier: string;
  principle: string;
  title: string;
  status: QuestionStatus;
  score: number;
  /** Position in the category/pillar tree, used to navigate back to it */
  categoryIndex: number;
  pillarIndex: number;
  questionIndex: number;
}

export interface PillarResult {
  id: string;
  name: string;
  description: string;
  /** Index of the pillar inside its category */
  pillarIndex: number;
  totalQuestions: number;
  answeredQuestions: number;
  score: number;
  maxScore: number;
  scorePercentage: number;
  statusBreakdown: StatusBreakdown;
  questions: QuestionResult[];
}

export interface CategoryResult {
  id: string;
  name: string;
  description: string;
  /** Index of the category in the assessment's filtered tree */
  categoryIndex: number;
  totalQuestions: number;
  answeredQuestions: number;
  score: number;
  maxScore: number;
  scorePercentage: number;
  statusBreakdown: StatusBreakdown;
  pillars: PillarResult[];
}

export interface OverallResult {
  totalQuestions: number;
  answeredQuestions: number;
  completionPercentage: number;
  totalScore: number;
  maxPossibleScore: number;
  scorePercentage: number;
  statusBreakdown: StatusBreakdown;
}

export interface AssessmentResults {
  assessmentId: string;
  assessmentName: string;
  categories: string[];
  createdAt: string;
  updatedAt: string;
  categoryResults: CategoryResult[];
  overall: OverallResult;
}

/** One principle's aggregated score inside a pillar */
export interface PrincipleGroup {
  principle: string;
  score: number;
  maxScore: number;
  percentage: number;
  questions: QuestionResult[];
}

/** A pillar broken down by principle, for the analysis section */
export interface PillarPrincipleGroups {
  categoryIndex: number;
  pillarName: string;
  pillarIndex: number;
  score: number;
  maxScore: number;
  percentage: number;
  principles: PrincipleGroup[];
}

/** A category broken down by pillar, for the analysis section */
export interface CategoryPrincipleGroups {
  categoryName: string;
  categoryIndex: number;
  score: number;
  maxScore: number;
  percentage: number;
  pillars: PillarPrincipleGroups[];
}

/** A question still needing an answer, with where to find it */
export interface UnansweredQuestion {
  categoryName: string;
  categoryIndex: number;
  pillarName: string;
  pillarIndex: number;
  questionIndex: number;
  identifier: string;
  title: string;
}
