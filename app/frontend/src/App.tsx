/**
 * Application root: owns page/modal navigation state and composes the pages.
 */

import { css } from '@emotion/react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppFooter } from '@/components/layout/AppFooter';
import { AppHeader } from '@/components/layout/AppHeader';
import { AssessmentDocumentsModal } from '@/components/assessments/AssessmentDocumentsModal';
import { AssessmentFormModal } from '@/components/assessments/AssessmentFormModal';
import { AssessmentManagerModal } from '@/components/assessments/AssessmentManagerModal';
import { ImportAssessmentModal } from '@/components/assessments/ImportAssessmentModal';
import { filterCategories } from '@/core/pillars';
import { generateDemoAnswers } from '@/core/demoData';
import { useWafData } from '@/hooks/useWafData';
import { HomePage } from '@/pages/home/HomePage';
import { AssessmentPage } from '@/pages/assessment/AssessmentPage';
import { ResultsPage } from '@/pages/results/ResultsPage';
import {
  useAssessmentStore,
  useAssessmentsByRecent,
  useCurrentAssessment,
  useLoadAssessments,
} from '@/store/assessmentStore';
import { agentApi } from '@/store/api';
import { colors, fontSizes, spacing } from '@/styles/theme';
import type { AssessmentDraft } from '@/types/waf';
import type { PageName, QuestionPosition } from '@/types/navigation';

/** Which modal, if any, is open. 'create-docs' is the document step shown right
 * after creation, before the agents are triggered. */
type ActiveModal =
  | 'manager'
  | 'create'
  | 'edit'
  | 'import'
  | 'documents'
  | 'create-docs'
  | null;

const appCss = css({
  minHeight: '100vh',
  display: 'flex',
  flexDirection: 'column',
});

const mainCss = css({
  flex: 1,
});

const statusCss = css({
  padding: `${spacing['2xl']} ${spacing.sm}`,
  textAlign: 'center',
  color: colors.textLight,
});

const errorTitleCss = css({
  color: colors.error,
  fontSize: fontSizes.xl,
  marginBottom: spacing.xs,
});

const START_POSITION: QuestionPosition = { categoryIndex: 0, pillarIndex: 0, questionIndex: 0 };

export const App = () => {
  const { data, isLoading, error } = useWafData();

  const [currentPage, setCurrentPage] = useState<PageName>('home');
  const [activeModal, setActiveModal] = useState<ActiveModal>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [position, setPosition] = useState<QuestionPosition>(START_POSITION);

  useLoadAssessments();

  const assessment = useCurrentAssessment();
  const assessments = useAssessmentsByRecent();
  const currentAssessmentId = useAssessmentStore((state) => state.currentAssessmentId);
  const createAssessment = useAssessmentStore((state) => state.createAssessment);
  const updateAssessment = useAssessmentStore((state) => state.updateAssessment);
  const deleteAssessment = useAssessmentStore((state) => state.deleteAssessment);
  const importAssessment = useAssessmentStore((state) => state.importAssessment);
  const selectAssessment = useAssessmentStore((state) => state.selectAssessment);

  /** Question tree scoped to the active assessment's selected categories */
  const categories = useMemo(() => {
    if (!data) return [];
    if (!assessment) return data.categories;
    return filterCategories(data.categories, assessment.categories);
  }, [data, assessment]);

  // Start from the top whenever the active assessment changes
  useEffect(() => {
    setPosition(START_POSITION);
  }, [currentAssessmentId]);

  const closeModal = useCallback(() => {
    setActiveModal(null);
    setEditingId(null);
  }, []);

  const handleCreate = useCallback(
    async (draft: AssessmentDraft, generateDemoData: boolean) => {
      const demoAnswers =
        generateDemoData && data
          ? generateDemoAnswers(filterCategories(data.categories, draft.categories))
          : undefined;

      // Defer the agents: land on the document step first so files can be
      // attached, then handleStartAnalysis triggers the run with them in place.
      await createAssessment(draft, demoAnswers, false);
      setActiveModal('create-docs');
    },
    [createAssessment, data],
  );

  // Close the creation document step and kick off the agents for the new
  // assessment. Reached from the step's "Start analysis" action or any dismissal.
  const handleStartAnalysis = useCallback(async () => {
    if (currentAssessmentId) {
      // Best-effort, like creation used to be: a trigger failure shouldn't trap
      // the user in the modal.
      try {
        await agentApi.runAll(currentAssessmentId);
      } catch {
        // ignore — the assessment still exists; agents can be rerun per layer
      }
    }
    closeModal();
    setCurrentPage('assessment');
  }, [currentAssessmentId, closeModal]);

  const handleUpdate = useCallback(
    async (draft: AssessmentDraft) => {
      if (!editingId) return;
      await updateAssessment(editingId, draft);
      // The category filter may have changed the question list
      setPosition(START_POSITION);
      closeModal();
    },
    [editingId, updateAssessment, closeModal],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      const target = assessments.find((entry) => entry.id === id);
      if (!target) return;
      const message =
        `Are you sure you want to delete "${target.name}"?\n\n` +
        'This action cannot be undone.';
      if (!window.confirm(message)) return;
      await deleteAssessment(id);
    },
    [assessments, deleteAssessment],
  );

  const handleNavigateToQuestion = useCallback((next: QuestionPosition) => {
    setPosition(next);
    setCurrentPage('assessment');
  }, []);

  const editingAssessment = editingId
    ? assessments.find((entry) => entry.id === editingId) ?? null
    : null;

  if (isLoading) {
    return (
      <div css={appCss}>
        <p css={statusCss}>Loading...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div css={appCss}>
        <div css={statusCss} role="alert">
          <h1 css={errorTitleCss}>Failed to load application</h1>
          <p>There was an error loading the assessment data. Please try refreshing the page.</p>
        </div>
      </div>
    );
  }

  return (
    <div css={appCss}>
      <AppHeader
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        onOpenAssessmentManager={() => setActiveModal('manager')}
      />

      <main css={mainCss}>
        {currentPage === 'home' && (
          <HomePage onStartAssessment={() => setActiveModal('manager')} />
        )}

        {currentPage === 'assessment' && (
          <AssessmentPage
            assessment={assessment}
            categories={categories}
            position={position}
            onPositionChange={setPosition}
            onFinish={() => setCurrentPage('results')}
            onCreateAssessment={() => setActiveModal('create')}
            onOpenAssessmentManager={() => setActiveModal('manager')}
            onEditAssessment={() => {
              if (!assessment) return;
              setEditingId(assessment.id);
              setActiveModal('edit');
            }}
            onOpenDocuments={() => setActiveModal('documents')}
          />
        )}

        {currentPage === 'results' && (
          <ResultsPage
            assessment={assessment}
            categories={categories}
            onOpenAssessmentManager={() => setActiveModal('manager')}
            onContinueAssessment={() => setCurrentPage('assessment')}
            onNavigateToQuestion={handleNavigateToQuestion}
          />
        )}
      </main>

      <AppFooter />

      {activeModal === 'manager' && (
        <AssessmentManagerModal
          assessments={assessments}
          currentAssessmentId={currentAssessmentId}
          onClose={closeModal}
          onCreate={() => setActiveModal('create')}
          onImport={() => setActiveModal('import')}
          onLoad={(id) => {
            selectAssessment(id);
            closeModal();
            setCurrentPage('assessment');
          }}
          onEdit={(id) => {
            setEditingId(id);
            setActiveModal('edit');
          }}
          onDelete={handleDelete}
        />
      )}

      {activeModal === 'create' && (
        <AssessmentFormModal onSubmit={handleCreate} onClose={closeModal} />
      )}

      {activeModal === 'edit' && editingAssessment && (
        <AssessmentFormModal
          initialValues={{
            name: editingAssessment.name,
            description: editingAssessment.description,
            categories: editingAssessment.categories,
            cloudProvider: editingAssessment.cloudProvider,
          }}
          onSubmit={handleUpdate}
          onClose={closeModal}
        />
      )}

      {activeModal === 'import' && (
        <ImportAssessmentModal
          onImport={async (imported) => {
            const created = await importAssessment(imported);
            closeModal();
            setCurrentPage('assessment');
            window.alert(`Assessment "${created.name}" imported successfully!`);
          }}
          onClose={closeModal}
        />
      )}

      {(activeModal === 'documents' || activeModal === 'create-docs') && assessment && (
        <AssessmentDocumentsModal
          assessmentId={assessment.id}
          assessmentName={assessment.name}
          onClose={closeModal}
          onStartAnalysis={
            activeModal === 'create-docs' ? handleStartAnalysis : undefined
          }
        />
      )}
    </div>
  );
};
