/**
 * Question status definitions.
 * Single source of truth for the status values, their score weight, and which
 * of them count as answered.
 */

import type { AgentVerdict, QuestionStatus } from '@/types/waf';

/** Status of a question that has not been answered yet */
export const DEFAULT_STATUS: QuestionStatus = 'answer-later';

/**
 * The agent's compliance verdict expressed as the equivalent WAF workflow
 * status, so an agent finding is classified and coloured the same way a reviewer's
 * own answer is. There are three categories: a met requirement reads as
 * "Completed", a partial one as "In Progress", and an unmet one as "Open".
 *
 * `unknown` has no equivalent and is deliberately omitted: it means the agent
 * could not classify the question (no signal or no check), which is distinct
 * from a reviewer choosing to answer it later - so callers handle it as a neutral
 * "needs review" state rather than a status.
 */
export const VERDICT_STATUS: Record<Exclude<AgentVerdict, 'unknown'>, QuestionStatus> = {
  met: 'completed',
  partial: 'in-progress',
  not_met: 'open',
};

/** Maximum score a single question can reach */
export const MAX_QUESTION_SCORE = 3;

export interface StatusDefinition {
  value: QuestionStatus;
  score: number;
  /** Label shown on the status selector and in badges */
  label: string;
  /** Whether picking this status counts the question as answered */
  counted: boolean;
}

/** Selectable statuses, in display order */
export const STATUS_DEFINITIONS: readonly StatusDefinition[] = [
  { value: 'answer-later', score: 0, label: 'Answer later', counted: false },
  { value: 'open', score: 1, label: 'Open', counted: true },
  { value: 'in-progress', score: 2, label: 'In Progress', counted: true },
  { value: 'completed', score: 3, label: 'Completed', counted: true },
  { value: 'ignore', score: 0, label: 'Ignore', counted: true },
];

/**
 * Label for a status value
 */
export function getStatusLabel(status: QuestionStatus): string {
  return STATUS_DEFINITIONS.find((definition) => definition.value === status)?.label ?? status;
}

/**
 * Get the score contributed by a status
 */
export function getStatusScore(status: QuestionStatus): number {
  return STATUS_DEFINITIONS.find((definition) => definition.value === status)?.score ?? 0;
}

/**
 * Whether a status counts the question as answered.
 * Missing values and "answer-later" do not count.
 */
export function isAnswered(status: QuestionStatus | undefined): boolean {
  if (!status) return false;
  return STATUS_DEFINITIONS.find((definition) => definition.value === status)?.counted ?? false;
}
