/**
 * Assessment import/export.
 *
 * Imported files are untrusted input, so the shape is validated with type
 * guards rather than an `as` cast.
 */

import type {
  Assessment,
  AssessmentAnswers,
  AssessmentNotes,
  CloudProvider,
  QuestionStatus,
} from '@/types/waf';
import { STATUS_DEFINITIONS } from './status';

const VALID_STATUSES = new Set<string>(STATUS_DEFINITIONS.map((definition) => definition.value));
const VALID_PROVIDERS = new Set<string>(['aws', 'azure', 'gcp']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === 'string');
}

function toCloudProvider(value: unknown): CloudProvider | null {
  if (typeof value !== 'string' || !VALID_PROVIDERS.has(value)) return null;
  // Narrowed by the set membership check above
  if (value === 'aws' || value === 'azure' || value === 'gcp') return value;
  return null;
}

/**
 * Coerce a raw value to a known status, or null when unrecognized.
 */
function toStatus(value: unknown): QuestionStatus | null {
  if (typeof value !== 'string' || !VALID_STATUSES.has(value)) return null;

  for (const definition of STATUS_DEFINITIONS) {
    if (definition.value === value) return definition.value;
  }
  return null;
}

/**
 * Pick out the valid `categoryId -> pillarId -> questionId -> status` entries,
 * dropping anything that does not match a known status.
 */
function parseAnswers(value: unknown): AssessmentAnswers {
  if (!isRecord(value)) return {};

  const answers: AssessmentAnswers = {};

  for (const [categoryId, categoryValue] of Object.entries(value)) {
    if (!isRecord(categoryValue)) continue;

    const categoryAnswers: Record<string, Record<string, QuestionStatus>> = {};
    for (const [pillarId, pillarValue] of Object.entries(categoryValue)) {
      if (!isRecord(pillarValue)) continue;

      const pillarAnswers: Record<string, QuestionStatus> = {};
      for (const [questionId, status] of Object.entries(pillarValue)) {
        const parsed = toStatus(status);
        if (parsed) pillarAnswers[questionId] = parsed;
      }

      if (Object.keys(pillarAnswers).length > 0) {
        categoryAnswers[pillarId] = pillarAnswers;
      }
    }

    if (Object.keys(categoryAnswers).length > 0) {
      answers[categoryId] = categoryAnswers;
    }
  }

  return answers;
}

/**
 * Pick out the valid `categoryId -> pillarId -> questionId -> note` entries,
 * keeping only non-empty string notes and dropping anything else.
 */
function parseNotes(value: unknown): AssessmentNotes {
  if (!isRecord(value)) return {};

  const notes: AssessmentNotes = {};

  for (const [categoryId, categoryValue] of Object.entries(value)) {
    if (!isRecord(categoryValue)) continue;

    const categoryNotes: Record<string, Record<string, string>> = {};
    for (const [pillarId, pillarValue] of Object.entries(categoryValue)) {
      if (!isRecord(pillarValue)) continue;

      const pillarNotes: Record<string, string> = {};
      for (const [questionId, note] of Object.entries(pillarValue)) {
        if (typeof note === 'string' && note.trim() !== '') {
          pillarNotes[questionId] = note;
        }
      }

      if (Object.keys(pillarNotes).length > 0) {
        categoryNotes[pillarId] = pillarNotes;
      }
    }

    if (Object.keys(categoryNotes).length > 0) {
      notes[categoryId] = categoryNotes;
    }
  }

  return notes;
}

/**
 * Parse an exported assessment file.
 *
 * @throws {Error} When the file is not a recognizable assessment
 */
export function parseAssessmentFile(text: string): Omit<Assessment, 'id'> {
  const parsed: unknown = JSON.parse(text);

  if (!isRecord(parsed) || typeof parsed.name !== 'string' || parsed.name.trim() === '') {
    throw new Error('Invalid assessment file format');
  }

  const now = new Date().toISOString();

  return {
    name: parsed.name,
    description: typeof parsed.description === 'string' ? parsed.description : '',
    categories: isStringArray(parsed.categories) ? parsed.categories : [],
    cloudProvider: toCloudProvider(parsed.cloudProvider),
    createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : now,
    updatedAt: now,
    importedAt: now,
    answers: parseAnswers(parsed.answers),
    notes: parseNotes(parsed.notes),
  };
}

/**
 * Build the filename used when exporting an assessment
 */
export function buildExportFileName(assessmentName: string): string {
  const slug = assessmentName
    .replace(/[^a-z0-9]/gi, '-')
    .toLowerCase()
    .substring(0, 50);
  const date = new Date().toISOString().split('T')[0];

  return `waf-${slug}-${date}.json`;
}

/**
 * Download an assessment as a JSON file
 */
export function downloadAssessment(assessment: Assessment): void {
  const blob = new Blob([JSON.stringify(assessment, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = buildExportFileName(assessment.name);
  link.click();

  URL.revokeObjectURL(url);
}
