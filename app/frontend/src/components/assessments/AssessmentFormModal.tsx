/**
 * Create / edit assessment modal.
 * One form serves both; only creating offers the demo-data option.
 */

import { css } from '@emotion/react';
import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import { AVAILABLE_CATEGORIES } from '@/core/pillars';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { colors, fontSizes, radius, spacing, transitions } from '@/styles/theme';
import type { AssessmentDraft, CloudProvider } from '@/types/waf';

export interface AssessmentFormModalProps {
  /** Values to prefill; omit to create a new assessment */
  initialValues?: AssessmentDraft;
  onSubmit: (draft: AssessmentDraft, generateDemoData: boolean) => void;
  onClose: () => void;
}

const CLOUD_PROVIDERS: readonly { value: CloudProvider; label: string }[] = [
  { value: 'aws', label: 'Amazon Web Services (AWS)' },
  { value: 'azure', label: 'Microsoft Azure' },
  { value: 'gcp', label: 'Google Cloud Platform (GCP)' },
];

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

const controlCss = css({
  padding: '8px 10px',
  border: `2px solid ${colors.border}`,
  borderRadius: radius.md,
  fontSize: fontSizes.sm,
  transition: `border-color ${transitions.fast}`,

  '&:focus': {
    outline: 'none',
    borderColor: colors.primary,
  },
});

const hintCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const categoriesGridCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
  gap: '6px',
});

const checkboxCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  padding: '8px 10px',
  background: colors.background,
  border: `2px solid ${colors.border}`,
  borderRadius: radius.md,
  fontSize: fontSizes.sm,
  cursor: 'pointer',
  userSelect: 'none',
  transition: `all ${transitions.fast}`,

  '&:hover': {
    borderColor: colors.primary,
  },

  '&:has(input:checked)': {
    borderColor: colors.primary,
    color: colors.primaryText,
    fontWeight: 600,
  },
});

const footerCss = css({
  display: 'flex',
  justifyContent: 'flex-end',
  gap: spacing.xs,
  marginTop: spacing.md,
  paddingTop: spacing.sm,
  borderTop: `1px solid ${colors.borderLight}`,
});

const errorCss = css({
  padding: spacing.xs,
  marginBottom: spacing.sm,
  background: colors.errorLight,
  borderRadius: radius.md,
  color: colors.error,
  fontSize: fontSizes.sm,
});

export const AssessmentFormModal = ({
  initialValues,
  onSubmit,
  onClose,
}: AssessmentFormModalProps) => {
  const fieldPrefix = useId();
  const isEditing = initialValues !== undefined;

  const [name, setName] = useState(initialValues?.name ?? '');
  const [description, setDescription] = useState(initialValues?.description ?? '');
  const [categories, setCategories] = useState<string[]>(
    // New assessments start with every category selected
    initialValues?.categories ?? [...AVAILABLE_CATEGORIES],
  );
  const [cloudProvider, setCloudProvider] = useState<CloudProvider | null>(
    initialValues?.cloudProvider ?? null,
  );
  const [generateDemoData, setGenerateDemoData] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleCategory = (category: string) => {
    setCategories((current) =>
      current.includes(category)
        ? current.filter((entry) => entry !== category)
        : [...current, category],
    );
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (name.trim() === '') {
      setError('Please enter an assessment name');
      return;
    }

    if (categories.length === 0) {
      setError('Please select at least one architecture layer to assess');
      return;
    }

    onSubmit(
      { name: name.trim(), description: description.trim(), categories, cloudProvider },
      generateDemoData,
    );
  };

  const nameId = `${fieldPrefix}-name`;
  const descriptionId = `${fieldPrefix}-description`;
  const cloudId = `${fieldPrefix}-cloud`;

  return (
    <Modal title={isEditing ? 'Edit Assessment' : 'Create New Assessment'} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate>
        {error && <p css={errorCss}>{error}</p>}

        <div css={fieldCss}>
          <label css={labelCss} htmlFor={nameId}>
            Assessment Name *
          </label>
          <input
            id={nameId}
            css={controlCss}
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g., Client XYZ - Q4 2024"
            maxLength={100}
            autoComplete="off"
            required
          />
        </div>

        <div css={fieldCss}>
          <label css={labelCss} htmlFor={descriptionId}>
            Description
          </label>
          <textarea
            id={descriptionId}
            css={controlCss}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Add notes..."
            rows={2}
            maxLength={500}
          />
        </div>

        <fieldset css={[fieldCss, { border: 'none', padding: 0, margin: 0 }]}>
          <legend css={labelCss}>Architecture Layers to Assess *</legend>
          <div css={categoriesGridCss}>
            {AVAILABLE_CATEGORIES.map((category) => (
              <label key={category} css={checkboxCss}>
                <input
                  type="checkbox"
                  checked={categories.includes(category)}
                  onChange={() => toggleCategory(category)}
                />
                <span>{category}</span>
              </label>
            ))}
          </div>
          <small css={hintCss}>
            Each layer evaluates every WAF pillar. Select at least one layer.
          </small>
        </fieldset>

        <div css={fieldCss}>
          <label css={labelCss} htmlFor={cloudId}>
            Cloud Provider (optional)
          </label>
          <select
            id={cloudId}
            css={controlCss}
            value={cloudProvider ?? ''}
            onChange={(event) => {
              const { value } = event.target;
              const match = CLOUD_PROVIDERS.find((provider) => provider.value === value);
              setCloudProvider(match ? match.value : null);
            }}
          >
            <option value="">Not specified / Multi-cloud</option>
            {CLOUD_PROVIDERS.map((provider) => (
              <option key={provider.value} value={provider.value}>
                {provider.label}
              </option>
            ))}
          </select>
          <small css={hintCss}>Select the cloud provider to receive specific guidance in questions</small>
        </div>

        {!isEditing && (
          <div css={fieldCss}>
            <label css={checkboxCss}>
              <input
                type="checkbox"
                checked={generateDemoData}
                onChange={(event) => setGenerateDemoData(event.target.checked)}
              />
              <span>Generate demo data</span>
            </label>
            <small css={hintCss}>Automatically fills in answers with random data for demonstration purposes</small>
          </div>
        )}

        <div css={footerCss}>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit">
            {isEditing ? 'Save Changes' : 'Create Assessment'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
