/**
 * Domain types for the WAF assessment.
 *
 * `Category`, `Pillar`, and `Question` describe the shape of the data file in
 * the canonical `/data/waf-data.json`; the assessment types describe what the app persists.
 *
 * The question set is a three-level tree: an architecture-step `Category`
 * (Ingestion, Storage, …) contains every WAF `Pillar`, and each pillar holds
 * the `Question`s reworded for that step.
 */

/** Cloud providers a question can offer specific guidance for */
export type CloudProvider = 'aws' | 'azure' | 'gcp';

/** Status a question can be given, in display order */
export type QuestionStatus = 'answer-later' | 'open' | 'in-progress' | 'completed' | 'ignore';

export interface CloudSpecificInfo {
  concept: string;
  keyPoints?: string[];
  documentation?: string;
}

export interface DecisionFramework {
  title?: string;
  useCustomerManaged?: string[];
  useDefaultManaged?: string[];
}

export interface ChecklistCategory {
  category: string;
  questions: string[];
}

export interface AdditionalResource {
  title: string;
  url: string;
}

export interface DatabricksGuidance {
  context?: string;
  cloudSpecific?: Partial<Record<CloudProvider, CloudSpecificInfo>>;
  decisionFramework?: DecisionFramework;
  validationChecklist?: ChecklistCategory[];
  additionalResources?: AdditionalResource[];
}

export interface Question {
  id: string;
  identifier: string;
  principle: string;
  title: string;
  details?: string | null;
  databricksGuidance?: DatabricksGuidance | null;
}

export interface Pillar {
  id: string;
  name: string;
  description: string;
  questions: Question[];
}

/**
 * An architecture layer (Ingestion, Storage, …). Every category holds the full
 * set of WAF pillars, each with the questions reworded for that step.
 */
export interface Category {
  id: string;
  name: string;
  description: string;
  pillars: Pillar[];
}

/**
 * Answers for one assessment: category id -> pillar id -> question id -> status
 */
export type AssessmentAnswers = Record<string, Record<string, Record<string, QuestionStatus>>>;

/**
 * Free-text notes for one assessment, keyed exactly like answers:
 * category id -> pillar id -> question id -> note text. Sparse: only questions
 * with a non-empty note appear.
 */
export type AssessmentNotes = Record<string, Record<string, Record<string, string>>>;

export interface Assessment {
  id: string;
  name: string;
  description: string;
  categories: string[];
  cloudProvider: CloudProvider | null;
  createdAt: string;
  updatedAt: string;
  /** Set when the assessment came from an imported file */
  importedAt?: string;
  answers: AssessmentAnswers;
  notes: AssessmentNotes;
}

/** Input accepted when creating or editing an assessment */
export interface AssessmentDraft {
  name: string;
  description: string;
  categories: string[];
  cloudProvider: CloudProvider | null;
}

// -- Architecture documents -----------------------------------------------
// Files the user uploads to describe the assessment's architecture. The bytes
// live server-side (a UC Volume); the agents read them as extra evidence. `kind`
// is 'text' for extracted formats (pdf/txt/md/docx) and 'image' for diagrams.

export type DocumentKind = 'text' | 'image';

/** Metadata for one uploaded architecture document (never the bytes). */
export interface AssessmentDocument {
  id: string;
  assessmentId: string;
  filename: string;
  contentType: string;
  kind: DocumentKind;
  /** Size in bytes. */
  size: number;
  uploadedAt: string;
}

/** Documents for an assessment, plus whether uploading is available here. */
export interface DocumentsResponse {
  enabled: boolean;
  documents: AssessmentDocument[];
}

// -- Agent findings --------------------------------------------------------
// An agent proposes a compliance verdict for a question from workspace signals.
// This is separate from the workflow `QuestionStatus` above: the verdict says
// whether a practice looks implemented, not whether a human has dealt with it.

export type AgentVerdict = 'met' | 'partial' | 'not_met' | 'unknown';
export type AgentConfidence = 'high' | 'medium' | 'low' | 'none';
export type AgentRunStatus = 'queued' | 'running' | 'done' | 'failed';

/** One piece of support for a finding, shown in the Sources expander. */
export interface AgentEvidence {
  kind: string;
  summary: string;
  detail: string;
  rows: Record<string, unknown>[];
  ref: string | null;
}

/** The agent's answer for a single question. */
export interface AgentFinding {
  id: string;
  runId: string;
  categoryId: string;
  pillarId: string;
  questionId: string;
  verdict: AgentVerdict;
  score: number | null;
  confidence: AgentConfidence;
  rationale: string;
  sources: AgentEvidence[];
  autoAssessable: boolean;
  createdAt: string;
}

/** One execution of a layer agent. */
export interface AgentRun {
  runId: string;
  assessmentId: string;
  layer: string;
  status: AgentRunStatus;
  nTotal: number;
  nDone: number;
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
}

/** Findings for the latest run of a layer, keyed by question id. */
export interface AgentFindingsResponse {
  run: AgentRun | null;
  findings: Record<string, AgentFinding>;
}

// -- Implementation backlog ------------------------------------------------
// The results-level backlog agent reasons over the whole assessment and returns
// a prioritized list of implementation tasks. It runs on demand from the Results
// page (backend-driven, not a Databricks Job) and reuses the AgentRunStatus states.

/** Criticality / complexity band for a backlog task. */
export type BacklogSeverity = 'high' | 'medium' | 'low';

/** One prioritized task in the implementation backlog. */
export interface BacklogTask {
  title: string;
  description: string;
  /** WAF pillar this task belongs to. */
  pillar: string;
  /** Architecture layer this task belongs to (or "Cross-cutting"). */
  layer: string;
  criticality: BacklogSeverity;
  complexity: BacklogSeverity;
  /** Rough duration estimate, e.g. "1-2 weeks". */
  timeline: string;
  /** Overall order, 1 = do first. */
  priority: number;
  /** Titles of tasks that must come first. */
  dependsOn: string[];
}

/** One on-demand run of the backlog agent for an assessment. */
export interface BacklogRun {
  runId: string;
  assessmentId: string;
  status: AgentRunStatus;
  error: string | null;
  model: string | null;
  tasks: BacklogTask[];
  startedAt: string;
  finishedAt: string | null;
}

/** Latest backlog run for an assessment, or null when none has run. */
export interface BacklogResponse {
  run: BacklogRun | null;
}
