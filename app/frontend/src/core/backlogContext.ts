/**
 * Assemble the assessment context the backlog agent reasons over.
 *
 * The backend has the raw answers and agent findings but not the question tree or
 * the scoring logic (both live in the frontend), so the client builds this
 * compact, self-contained snapshot from the computed results plus the notes and
 * POSTs it; the backend enriches it with agent findings before prompting.
 */

import type { Assessment } from '@/types/waf';
import type { AssessmentResults } from '@/types/results';

export interface BacklogContextQuestion {
  id: string;
  identifier: string;
  title: string;
  status: string;
  note: string;
}

export interface BacklogContextPillar {
  name: string;
  scorePercentage: number;
  questions: BacklogContextQuestion[];
}

export interface BacklogContextLayer {
  name: string;
  scorePercentage: number;
  pillars: BacklogContextPillar[];
}

export interface BacklogContext {
  assessmentName: string;
  cloudProvider: string | null;
  overall: {
    scorePercentage: number;
    totalScore: number;
    maxPossibleScore: number;
    completionPercentage: number;
    answeredQuestions: number;
    totalQuestions: number;
  };
  layers: BacklogContextLayer[];
}

/**
 * Build the backlog context from an assessment's computed results and its notes.
 */
export function buildBacklogContext(
  results: AssessmentResults,
  assessment: Assessment,
): BacklogContext {
  const layers: BacklogContextLayer[] = results.categoryResults.map((category) => ({
    name: category.name,
    scorePercentage: category.scorePercentage,
    pillars: category.pillars.map((pillar) => ({
      name: pillar.name,
      scorePercentage: pillar.scorePercentage,
      questions: pillar.questions.map((question) => ({
        id: question.id,
        identifier: question.identifier,
        title: question.title,
        status: question.status,
        note: assessment.notes?.[category.id]?.[pillar.id]?.[question.id] ?? '',
      })),
    })),
  }));

  return {
    assessmentName: assessment.name,
    cloudProvider: assessment.cloudProvider,
    overall: {
      scorePercentage: results.overall.scorePercentage,
      totalScore: results.overall.totalScore,
      maxPossibleScore: results.overall.maxPossibleScore,
      completionPercentage: results.overall.completionPercentage,
      answeredQuestions: results.overall.answeredQuestions,
      totalQuestions: results.overall.totalQuestions,
    },
    layers,
  };
}
