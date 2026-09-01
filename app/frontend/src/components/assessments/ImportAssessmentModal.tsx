/**
 * Import assessment modal: restore an assessment from an exported JSON file.
 */

import { css } from '@emotion/react';
import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import { parseAssessmentFile } from '@/core/assessmentFile';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { colors, fontSizes, radius, spacing } from '@/styles/theme';
import type { Assessment } from '@/types/waf';

export interface ImportAssessmentModalProps {
  onImport: (assessment: Omit<Assessment, 'id'>) => void;
  onClose: () => void;
}

const fieldCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: '6px',
  marginBottom: spacing.sm,
});

const labelCss = css({
  fontSize: fontSizes.sm,
  fontWeight: 600,
});

const instructionsCss = css({
  marginBottom: spacing.sm,
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

const errorCss = css({
  padding: spacing.xs,
  marginBottom: spacing.sm,
  background: colors.errorLight,
  borderRadius: radius.md,
  color: colors.error,
  fontSize: fontSizes.sm,
});

const footerCss = css({
  display: 'flex',
  justifyContent: 'flex-end',
  gap: spacing.xs,
  marginTop: spacing.md,
});

export const ImportAssessmentModal = ({ onImport, onClose }: ImportAssessmentModalProps) => {
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    if (!file) {
      setError('Assessment File');
      return;
    }

    try {
      onImport(parseAssessmentFile(await file.text()));
    } catch (parseError) {
      console.error('Could not import the assessment', parseError);
      setError('Error importing assessment. Please ensure the file is a valid assessment JSON file.');
    }
  };

  return (
    <Modal title="Import Assessment" onClose={onClose} size="sm">
      <p css={instructionsCss}>Select a previously exported assessment JSON file to import.</p>

      <form
        onSubmit={(event) => {
          void handleSubmit(event);
        }}
      >
        {error && <p css={errorCss}>{error}</p>}

        <div css={fieldCss}>
          <label css={labelCss} htmlFor={inputId}>
            Assessment File *
          </label>
          <input
            id={inputId}
            type="file"
            accept=".json,application/json"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
        </div>

        <div css={footerCss}>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit">
            Import Assessment
          </Button>
        </div>
      </form>
    </Modal>
  );
};
