/**
 * Assessment manager modal: list, load, edit, export and delete assessments.
 */

import { css } from '@emotion/react';
import { downloadAssessment } from '@/core/assessmentFile';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { colors, fontSizes, radius, spacing } from '@/styles/theme';
import type { Assessment } from '@/types/waf';

export interface AssessmentManagerModalProps {
  assessments: Assessment[];
  currentAssessmentId: string | null;
  onClose: () => void;
  onCreate: () => void;
  onImport: () => void;
  onLoad: (id: string) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}

const actionsCss = css({
  display: 'flex',
  gap: spacing.xs,
  marginBottom: spacing.md,
  flexWrap: 'wrap',
});

const listHeadingCss = css({
  fontSize: fontSizes.sm,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: colors.textLight,
  marginBottom: spacing.xs,
});

const itemCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  padding: spacing.xs,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.md,
  marginBottom: '6px',
});

const activeItemCss = css({
  borderColor: colors.primary,
  background: `${colors.primary}0A`,
});

const nameRowCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  flexWrap: 'wrap',
});

const nameCss = css({
  fontSize: fontSizes.sm,
  fontWeight: 600,
});

const activeBadgeCss = css({
  padding: '1px 8px',
  borderRadius: radius.full,
  background: colors.primary,
  color: colors.textInverse,
  fontSize: '0.625rem',
  fontWeight: 700,
  textTransform: 'uppercase',
});

const metaCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const tagsCss = css({
  display: 'flex',
  gap: '4px',
  flexWrap: 'wrap',
  margin: '4px 0',
});

const tagCss = css({
  padding: '1px 6px',
  borderRadius: radius.full,
  background: colors.backgroundDark,
  color: colors.textLight,
  fontSize: '0.625rem',
});

const itemActionsCss = css({
  display: 'flex',
  gap: '2px',
  marginLeft: 'auto',
  flexShrink: 0,
});

const emptyCss = css({
  padding: spacing.md,
  textAlign: 'center',
  color: colors.textLight,
  fontSize: fontSizes.sm,
});

export const AssessmentManagerModal = ({
  assessments,
  currentAssessmentId,
  onClose,
  onCreate,
  onImport,
  onLoad,
  onEdit,
  onDelete,
}: AssessmentManagerModalProps) => {

  return (
    <Modal title="Assessment Manager" onClose={onClose} size="lg">
      <div css={actionsCss}>
        <Button variant="primary" onClick={onCreate}>
          + New Assessment
        </Button>
        <Button variant="secondary" onClick={onImport}>
          ↑ Import Assessment
        </Button>
      </div>

      {assessments.length === 0 ? (
        <p css={emptyCss}>No assessments yet. Create your first assessment to get started.</p>
      ) : (
        <>
          <h3 css={listHeadingCss}>Existing Assessments</h3>
          {assessments.map((assessment) => {
            const isActive = assessment.id === currentAssessmentId;

            return (
              <div key={assessment.id} css={[itemCss, isActive && activeItemCss]}>
                <div css={{ minWidth: 0 }}>
                  <div css={nameRowCss}>
                    <span css={nameCss}>{assessment.name}</span>
                    {isActive && <span css={activeBadgeCss}>Active</span>}
                  </div>
                  {assessment.categories.length > 0 && (
                    <div css={tagsCss}>
                      {assessment.categories.map((category) => (
                        <span key={category} css={tagCss}>
                          {category}
                        </span>
                      ))}
                    </div>
                  )}
                  <span css={metaCss}>
                    {new Date(assessment.createdAt).toLocaleDateString()}
                  </span>
                </div>

                <div css={itemActionsCss}>
                  {!isActive && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onLoad(assessment.id)}
                      aria-label={`Load: ${assessment.name}`}
                      title="Load"
                    >
                      <span aria-hidden="true">📂</span>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(assessment.id)}
                    aria-label={`Edit: ${assessment.name}`}
                    title="Edit"
                  >
                    <span aria-hidden="true">✏️</span>
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => downloadAssessment(assessment)}
                    aria-label={`Export: ${assessment.name}`}
                    title="Export"
                  >
                    <span aria-hidden="true">↓</span>
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => onDelete(assessment.id)}
                    aria-label={`Delete: ${assessment.name}`}
                    title="Delete"
                  >
                    <span aria-hidden="true">🗑</span>
                  </Button>
                </div>
              </div>
            );
          })}
        </>
      )}
    </Modal>
  );
};
