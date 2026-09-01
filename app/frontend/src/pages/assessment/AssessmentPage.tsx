/**
 * Assessment page: sidebar navigation plus the current question.
 */

import { css } from '@emotion/react';
import { useCallback } from 'react';
import { countQuestions } from '@/core/pillars';
import { calculatePillarProgress, findUnansweredQuestions } from '@/core/scoring';
import { DEFAULT_STATUS } from '@/core/status';
import { Button } from '@/components/ui/Button';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { useAgentFindings } from '@/hooks/useAgentFindings';
import { useAssessmentStore } from '@/store/assessmentStore';
import { colors, fontSizes, layout, radius, spacing } from '@/styles/theme';
import type { Assessment, Category, QuestionStatus } from '@/types/waf';
import type { QuestionPosition } from '@/types/navigation';
import { PillarsSidebar } from './PillarsSidebar';
import { QuestionView } from './QuestionView';

export interface AssessmentPageProps {
  assessment: Assessment | null;
  categories: Category[];
  position: QuestionPosition;
  onPositionChange: (position: QuestionPosition) => void;
  onFinish: () => void;
  onCreateAssessment: () => void;
  onOpenAssessmentManager: () => void;
  onEditAssessment: () => void;
}

const layoutCss = css({
  maxWidth: '1600px',
  margin: '0 auto',
  padding: spacing.sm,
  display: 'grid',
  gridTemplateColumns: 'minmax(240px, 300px) 1fr',
  gap: spacing.sm,
  alignItems: 'start',

  '@media (max-width: 900px)': {
    gridTemplateColumns: '1fr',
  },
});

const mainCss = css({
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  padding: spacing.md,
  minWidth: 0,
});

const pillarHeaderCss = css({
  display: 'flex',
  alignItems: 'flex-start',
  gap: spacing.sm,
  paddingBottom: spacing.sm,
  marginBottom: spacing.md,
  borderBottom: `1px solid ${colors.borderLight}`,
});

const categoryLabelCss = css({
  fontSize: fontSizes.xs,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: colors.primaryText,
  fontWeight: 700,
  marginBottom: '2px',
});

const pillarTitleCss = css({
  fontSize: fontSizes.lg,
});

const pillarDescriptionCss = css({
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

const progressBoxCss = css({
  minWidth: '140px',
  textAlign: 'right',
  flexShrink: 0,
});

const progressValueCss = css({
  fontSize: fontSizes.xl,
  fontWeight: 700,
  color: colors.primaryText,
  fontVariantNumeric: 'tabular-nums',
});

const progressLabelCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const navRowCss = css({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.sm,
  marginTop: spacing.lg,
  paddingTop: spacing.sm,
  borderTop: `1px solid ${colors.borderLight}`,
});

const counterCss = css({
  fontSize: fontSizes.sm,
  color: colors.textLight,
  fontVariantNumeric: 'tabular-nums',
});

const emptyStateCss = css({
  maxWidth: layout.containerMaxWidth,
  margin: '0 auto',
  padding: `${spacing['2xl']} ${spacing.sm}`,
  textAlign: 'center',
});

const emptyActionsCss = css({
  display: 'flex',
  gap: spacing.xs,
  justifyContent: 'center',
  marginTop: spacing.md,
  flexWrap: 'wrap',
});

export const AssessmentPage = ({
  assessment,
  categories,
  position,
  onPositionChange,
  onFinish,
  onCreateAssessment,
  onOpenAssessmentManager,
  onEditAssessment,
}: AssessmentPageProps) => {
  const setQuestionStatus = useAssessmentStore((state) => state.setQuestionStatus);
  const setQuestionNote = useAssessmentStore((state) => state.setQuestionNote);

  const currentCategory = categories[position.categoryIndex];
  const currentPillar = currentCategory?.pillars[position.pillarIndex];
  const currentQuestion = currentPillar?.questions[position.questionIndex];

  // Agent findings for the layer currently in view (category id = layer).
  const {
    run: agentRun,
    findings: agentFindings,
    refresh: rerunAgent,
  } = useAgentFindings(assessment?.id ?? null, currentCategory?.id ?? '');

  const handleStatusChange = useCallback(
    (status: QuestionStatus) => {
      if (!currentCategory || !currentPillar || !currentQuestion) return;
      setQuestionStatus(currentCategory.id, currentPillar.id, currentQuestion.id, status);
    },
    [currentCategory, currentPillar, currentQuestion, setQuestionStatus],
  );

  const handleNoteChange = useCallback(
    (note: string) => {
      if (!currentCategory || !currentPillar || !currentQuestion) return;
      setQuestionNote(currentCategory.id, currentPillar.id, currentQuestion.id, note);
    },
    [currentCategory, currentPillar, currentQuestion, setQuestionNote],
  );

  if (!assessment) {
    return (
      <div css={emptyStateCss}>
        <p css={{ fontSize: fontSizes['4xl'] }} aria-hidden="true">
          📋
        </p>
        <h2>No Assessment Selected</h2>
        <p css={{ color: colors.textLight }}>Create a new assessment or load an existing one to get started.</p>
        <div css={emptyActionsCss}>
          <Button variant="primary" onClick={onCreateAssessment}>
            Create New Assessment
          </Button>
          <Button variant="secondary" onClick={onOpenAssessmentManager}>
            Load Existing Assessment
          </Button>
        </div>
      </div>
    );
  }

  if (!currentCategory || !currentPillar || !currentQuestion) {
    return (
      <div css={emptyStateCss}>
        <h2>No Assessment Selected</h2>
        <p css={{ color: colors.textLight }}>Select at least one architecture layer</p>
        <div css={emptyActionsCss}>
          <Button variant="primary" onClick={onEditAssessment}>
            Edit Assessment
          </Button>
        </div>
      </div>
    );
  }

  const pillarAnswers = assessment.answers[currentCategory.id]?.[currentPillar.id];
  const status = pillarAnswers?.[currentQuestion.id] ?? DEFAULT_STATUS;
  const note = assessment.notes[currentCategory.id]?.[currentPillar.id]?.[currentQuestion.id] ?? '';
  const pillarProgress = calculatePillarProgress(currentPillar, pillarAnswers);

  // Absolute question number across every category and pillar
  const questionsBeforeCategory = categories
    .slice(0, position.categoryIndex)
    .reduce(
      (sum, category) =>
        sum + category.pillars.reduce((pillarSum, pillar) => pillarSum + pillar.questions.length, 0),
      0,
    );
  const questionsBeforePillar = currentCategory.pillars
    .slice(0, position.pillarIndex)
    .reduce((sum, pillar) => sum + pillar.questions.length, 0);
  const currentNumber =
    questionsBeforeCategory + questionsBeforePillar + position.questionIndex + 1;
  const totalQuestions = countQuestions(categories);

  const lastCategoryIndex = categories.length - 1;
  const lastPillarIndex = currentCategory.pillars.length - 1;
  const isFirstQuestion =
    position.categoryIndex === 0 && position.pillarIndex === 0 && position.questionIndex === 0;
  const isLastQuestion =
    position.categoryIndex === lastCategoryIndex &&
    position.pillarIndex === lastPillarIndex &&
    position.questionIndex === currentPillar.questions.length - 1;

  const goPrevious = () => {
    if (position.questionIndex > 0) {
      onPositionChange({ ...position, questionIndex: position.questionIndex - 1 });
      return;
    }

    if (position.pillarIndex > 0) {
      const previousPillar = currentCategory.pillars[position.pillarIndex - 1];
      onPositionChange({
        categoryIndex: position.categoryIndex,
        pillarIndex: position.pillarIndex - 1,
        questionIndex: Math.max(0, (previousPillar?.questions.length ?? 1) - 1),
      });
      return;
    }

    const previousCategory = categories[position.categoryIndex - 1];
    if (!previousCategory) return;
    const previousPillarIndex = previousCategory.pillars.length - 1;
    const previousPillar = previousCategory.pillars[previousPillarIndex];

    onPositionChange({
      categoryIndex: position.categoryIndex - 1,
      pillarIndex: previousPillarIndex,
      questionIndex: Math.max(0, (previousPillar?.questions.length ?? 1) - 1),
    });
  };

  const goNext = () => {
    if (position.questionIndex < currentPillar.questions.length - 1) {
      onPositionChange({ ...position, questionIndex: position.questionIndex + 1 });
      return;
    }

    if (position.pillarIndex < lastPillarIndex) {
      onPositionChange({
        categoryIndex: position.categoryIndex,
        pillarIndex: position.pillarIndex + 1,
        questionIndex: 0,
      });
      return;
    }

    if (position.categoryIndex < lastCategoryIndex) {
      onPositionChange({
        categoryIndex: position.categoryIndex + 1,
        pillarIndex: 0,
        questionIndex: 0,
      });
      return;
    }

    // At the end: only finish once every question has an answer
    const unanswered = findUnansweredQuestions(assessment, categories);
    const first = unanswered[0];

    if (first) {
      const message =
        `You have ${unanswered.length} unanswered question(s).\n\n` +
        `First unanswered: ${first.identifier} - ${first.title}\n\n` +
        'Please answer all questions before completing the assessment.\n\n' +
        'Go to first unanswered question?';

      if (window.confirm(message)) {
        onPositionChange({
          categoryIndex: first.categoryIndex,
          pillarIndex: first.pillarIndex,
          questionIndex: first.questionIndex,
        });
      }
      return;
    }

    window.alert('Congratulations! You have completed all questions! View your results in the Results page.');
    onFinish();
  };

  return (
    <div css={layoutCss}>
      <PillarsSidebar
        categories={categories}
        answers={assessment.answers}
        position={position}
        onNavigate={onPositionChange}
      />

      <main css={mainCss}>
        <header css={pillarHeaderCss}>
          <div css={{ flex: 1, minWidth: 0 }}>
            <div css={categoryLabelCss}>{currentCategory.name}</div>
            <h1 css={pillarTitleCss}>{currentPillar.name}</h1>
            <p css={pillarDescriptionCss}>{currentPillar.description}</p>
          </div>
          <div css={progressBoxCss}>
            <div css={progressValueCss}>{pillarProgress}%</div>
            <ProgressBar
              percentage={pillarProgress}
              label={`${currentPillar.name}: ${pillarProgress}%`}
            />
            <div css={progressLabelCss}>
              {currentPillar.questions.filter((q) => {
                const value = pillarAnswers?.[q.id];
                return value !== undefined && value !== DEFAULT_STATUS;
              }).length}{' '}
              of {currentPillar.questions.length}
            </div>
          </div>
        </header>

        <QuestionView
          category={currentCategory}
          pillar={currentPillar}
          question={currentQuestion}
          status={status}
          note={note}
          cloudProvider={assessment.cloudProvider}
          onStatusChange={handleStatusChange}
          onNoteChange={handleNoteChange}
          onEditAssessment={onEditAssessment}
          agentFinding={agentFindings[currentQuestion.id]}
          agentRun={agentRun}
          onRerunAgent={rerunAgent}
        />

        <div css={navRowCss}>
          <Button variant="secondary" onClick={goPrevious} disabled={isFirstQuestion}>
            ← Previous
          </Button>
          <span css={counterCss}>
            Question {currentNumber} of {totalQuestions}
          </span>
          <Button variant="primary" onClick={goNext}>
            {isLastQuestion ? 'Finish Assessment' : 'Next →'}
          </Button>
        </div>
      </main>
    </div>
  );
};
