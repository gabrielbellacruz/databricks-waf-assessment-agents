/**
 * Assessment store.
 *
 * Holds every assessment plus which one is active. Assessments are persisted
 * server-side in Lakebase via the API (see store/api.ts) and shared org-wide;
 * this store is an in-memory cache of that server state, loaded once on startup.
 *
 * Mutations call the API and fold the server's response back into the cache.
 * `setQuestionStatus` updates optimistically so clicking through questions stays
 * snappy, then reconciles with the server's copy.
 */

import { useEffect, useMemo } from 'react';
import { create } from 'zustand';
import { assessmentApi } from '@/store/api';
import type {
  Assessment,
  AssessmentAnswers,
  AssessmentDraft,
  QuestionStatus,
} from '@/types/waf';

export interface AssessmentState {
  assessments: Record<string, Assessment>;
  currentAssessmentId: string | null;
  isLoaded: boolean;

  loadAssessments: () => Promise<void>;
  createAssessment: (
    draft: AssessmentDraft,
    demoAnswers?: AssessmentAnswers,
    runAgents?: boolean,
  ) => Promise<Assessment>;
  updateAssessment: (id: string, draft: AssessmentDraft) => Promise<void>;
  deleteAssessment: (id: string) => Promise<void>;
  importAssessment: (assessment: Omit<Assessment, 'id'>) => Promise<Assessment>;
  selectAssessment: (id: string) => void;
  setQuestionStatus: (
    categoryId: string,
    pillarId: string,
    questionId: string,
    status: QuestionStatus,
  ) => Promise<void>;
  setQuestionNote: (
    categoryId: string,
    pillarId: string,
    questionId: string,
    note: string,
  ) => Promise<void>;
}

export const useAssessmentStore = create<AssessmentState>()((set, get) => ({
  assessments: {},
  currentAssessmentId: null,
  isLoaded: false,

  loadAssessments: async () => {
    const list = await assessmentApi.list();
    const assessments: Record<string, Assessment> = {};
    for (const a of list) assessments[a.id] = a;
    set({ assessments, isLoaded: true });
  },

  createAssessment: async (draft, demoAnswers, runAgents = true) => {
    const assessment = await assessmentApi.create({
      ...draft,
      answers: demoAnswers ?? {},
      runAgents,
    });
    set((state) => ({
      assessments: { ...state.assessments, [assessment.id]: assessment },
      currentAssessmentId: assessment.id,
    }));
    return assessment;
  },

  updateAssessment: async (id, draft) => {
    if (!get().assessments[id]) return;
    const updated = await assessmentApi.update(id, draft);
    set((state) => ({ assessments: { ...state.assessments, [id]: updated } }));
  },

  deleteAssessment: async (id) => {
    await assessmentApi.remove(id);
    set((state) => {
      const next = { ...state.assessments };
      delete next[id];
      return {
        assessments: next,
        currentAssessmentId:
          state.currentAssessmentId === id ? null : state.currentAssessmentId,
      };
    });
  },

  importAssessment: async (incoming) => {
    const assessment = await assessmentApi.create({
      name: incoming.name,
      description: incoming.description,
      categories: incoming.categories,
      cloudProvider: incoming.cloudProvider,
      answers: incoming.answers,
      notes: incoming.notes,
      importedAt: new Date().toISOString(),
    });
    set((state) => ({
      assessments: { ...state.assessments, [assessment.id]: assessment },
      currentAssessmentId: assessment.id,
    }));
    return assessment;
  },

  selectAssessment: (id) => {
    if (!get().assessments[id]) return;
    set({ currentAssessmentId: id });
  },

  setQuestionStatus: async (categoryId, pillarId, questionId, status) => {
    const { currentAssessmentId, assessments } = get();
    if (!currentAssessmentId) return;

    const assessment = assessments[currentAssessmentId];
    if (!assessment) return;

    // Optimistic update so the UI reflects the click immediately.
    const optimistic: Assessment = {
      ...assessment,
      updatedAt: new Date().toISOString(),
      answers: {
        ...assessment.answers,
        [categoryId]: {
          ...assessment.answers[categoryId],
          [pillarId]: {
            ...assessment.answers[categoryId]?.[pillarId],
            [questionId]: status,
          },
        },
      },
    };
    set((state) => ({
      assessments: { ...state.assessments, [currentAssessmentId]: optimistic },
    }));

    try {
      const saved = await assessmentApi.setStatus(
        currentAssessmentId,
        categoryId,
        pillarId,
        questionId,
        status,
      );
      set((state) => ({
        assessments: { ...state.assessments, [currentAssessmentId]: saved },
      }));
    } catch (error) {
      // Roll back to the pre-click state so the cache doesn't drift from server.
      set((state) => ({
        assessments: { ...state.assessments, [currentAssessmentId]: assessment },
      }));
      throw error;
    }
  },

  setQuestionNote: async (categoryId, pillarId, questionId, note) => {
    const { currentAssessmentId, assessments } = get();
    if (!currentAssessmentId) return;

    const assessment = assessments[currentAssessmentId];
    if (!assessment) return;

    // Optimistic update so the textarea reflects the edit immediately, mirroring
    // setQuestionStatus. The server's canonical (sparse) tree reconciles on save.
    const optimistic: Assessment = {
      ...assessment,
      updatedAt: new Date().toISOString(),
      notes: {
        ...assessment.notes,
        [categoryId]: {
          ...assessment.notes[categoryId],
          [pillarId]: {
            ...assessment.notes[categoryId]?.[pillarId],
            [questionId]: note,
          },
        },
      },
    };
    set((state) => ({
      assessments: { ...state.assessments, [currentAssessmentId]: optimistic },
    }));

    try {
      const saved = await assessmentApi.setNote(
        currentAssessmentId,
        categoryId,
        pillarId,
        questionId,
        note,
      );
      set((state) => ({
        assessments: { ...state.assessments, [currentAssessmentId]: saved },
      }));
    } catch (error) {
      // Roll back to the pre-edit state so the cache doesn't drift from server.
      set((state) => ({
        assessments: { ...state.assessments, [currentAssessmentId]: assessment },
      }));
      throw error;
    }
  },
}));

/**
 * Load the shared assessments from the server once, on mount. Call this near the
 * app root; subsequent renders reuse the cache.
 */
export function useLoadAssessments(): boolean {
  const isLoaded = useAssessmentStore((state) => state.isLoaded);
  const loadAssessments = useAssessmentStore((state) => state.loadAssessments);

  useEffect(() => {
    if (!isLoaded) void loadAssessments();
  }, [isLoaded, loadAssessments]);

  return isLoaded;
}

/**
 * Select the active assessment, or null when none is selected
 */
export function useCurrentAssessment(): Assessment | null {
  return useAssessmentStore((state) =>
    state.currentAssessmentId ? state.assessments[state.currentAssessmentId] ?? null : null,
  );
}

/**
 * Select the assessments sorted by most recently updated.
 *
 * The sort happens in `useMemo` rather than in the selector: a selector must
 * return a stable reference, and sorting builds a new array on every call.
 */
export function useAssessmentsByRecent(): Assessment[] {
  const assessments = useAssessmentStore((state) => state.assessments);

  return useMemo(
    () =>
      Object.values(assessments).sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    [assessments],
  );
}
