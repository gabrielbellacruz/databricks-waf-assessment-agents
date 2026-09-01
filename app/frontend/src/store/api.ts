/**
 * Assessment API client.
 *
 * Talks to the Flask backend (see backend/server) which persists to Lakebase.
 * The app is served from the same origin as the API, so requests are relative.
 * JSON is camelCase on both sides, matching the `Assessment` type.
 */

import type { BacklogContext } from '@/core/backlogContext';
import type {
  AgentFindingsResponse,
  AgentRun,
  Assessment,
  AssessmentAnswers,
  AssessmentDraft,
  AssessmentNotes,
  BacklogResponse,
  QuestionStatus,
} from '@/types/waf';

const BASE = '/api';

// Guard so a genuinely-unauthenticated user can't get stuck in a reload loop:
// only re-auth if we haven't already tried in the last few seconds.
const REAUTH_KEY = 'waf-last-reauth';
const REAUTH_COOLDOWN_MS = 10_000;

/**
 * The app is served behind the Databricks Apps OAuth proxy. When the browser
 * session expires the proxy returns 401 for fetch/XHR (it can't redirect an XHR
 * to the login page). A full network navigation re-runs the OAuth handshake and
 * restores the session - so on 401 we navigate to re-authenticate.
 *
 * But this is a PWA: the service worker's navigation route serves the cached
 * index.html for reloads *without hitting the network*, so a plain reload never
 * reaches the OAuth proxy and the stale session sticks. So we first unregister
 * the service worker and drop its caches, forcing the reload onto the network.
 * The cooldown prevents an endless loop if auth genuinely can't be established.
 */
async function reauthenticate(): Promise<void> {
  if (typeof window === 'undefined') return;
  const last = Number(sessionStorage.getItem(REAUTH_KEY) ?? 0);
  if (Date.now() - last <= REAUTH_COOLDOWN_MS) return;
  sessionStorage.setItem(REAUTH_KEY, String(Date.now()));

  try {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if ('caches' in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } finally {
    window.location.reload();
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (response.status === 401) {
    void reauthenticate();
    throw new Error(`API ${init?.method ?? 'GET'} ${path} failed: 401 (re-authenticating)`);
  }
  if (!response.ok) {
    throw new Error(`API ${init?.method ?? 'GET'} ${path} failed: ${response.status}`);
  }
  return response;
}

/** Parse a JSON response body into T. Callers know the shape for each endpoint. */
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  return response.json();
}

/** Payload for creating an assessment, including any pre-filled answers */
export interface CreateAssessmentPayload extends AssessmentDraft {
  answers?: AssessmentAnswers;
  notes?: AssessmentNotes;
  importedAt?: string;
}

export const assessmentApi = {
  list: () => requestJson<Assessment[]>('/assessments'),

  create: (payload: CreateAssessmentPayload) =>
    requestJson<Assessment>('/assessments', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  update: (id: string, draft: AssessmentDraft) =>
    requestJson<Assessment>(`/assessments/${id}`, {
      method: 'PUT',
      body: JSON.stringify(draft),
    }),

  remove: async (id: string): Promise<void> => {
    await send(`/assessments/${id}`, { method: 'DELETE' });
  },

  setStatus: (
    id: string,
    categoryId: string,
    pillarId: string,
    questionId: string,
    status: QuestionStatus,
  ) =>
    requestJson<Assessment>(`/assessments/${id}/answers`, {
      method: 'PUT',
      body: JSON.stringify({ categoryId, pillarId, questionId, status }),
    }),

  setNote: (
    id: string,
    categoryId: string,
    pillarId: string,
    questionId: string,
    note: string,
  ) =>
    requestJson<Assessment>(`/assessments/${id}/notes`, {
      method: 'PUT',
      body: JSON.stringify({ categoryId, pillarId, questionId, note }),
    }),
};

export const agentApi = {
  /** Trigger (or reuse) an agent run for a layer. */
  run: (assessmentId: string, layer: string) =>
    send(`/assessments/${assessmentId}/agents/${layer}/run`, { method: 'POST' }),

  /** Latest run status for a layer, or null when none has run. */
  getRun: async (assessmentId: string, layer: string): Promise<AgentRun | null> => {
    const response = await send(`/assessments/${assessmentId}/agents/${layer}/run`);
    if (response.status === 204) return null;
    return response.json();
  },

  /** Findings from the latest run for a layer, keyed by question id. */
  getFindings: (assessmentId: string, layer: string) =>
    requestJson<AgentFindingsResponse>(`/assessments/${assessmentId}/agents/${layer}/findings`),
};

export const backlogApi = {
  /** Generate (or reuse an in-flight) implementation backlog for an assessment. */
  run: (assessmentId: string, context: BacklogContext) =>
    send(`/assessments/${assessmentId}/backlog/run`, {
      method: 'POST',
      body: JSON.stringify(context),
    }),

  /** Latest backlog run for an assessment, with its tasks. */
  get: (assessmentId: string) =>
    requestJson<BacklogResponse>(`/assessments/${assessmentId}/backlog`),
};
