/**
 * Architecture documents modal: upload, list, download, and delete the files
 * that describe an assessment's architecture. The agents read these as extra
 * context when answering that assessment's questions.
 */

import { css } from '@emotion/react';
import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useAssessmentDocuments } from '@/hooks/useAssessmentDocuments';
import { documentApi } from '@/store/api';
import { colors, fontSizes, radius, spacing } from '@/styles/theme';
import type { AssessmentDocument } from '@/types/waf';

export interface AssessmentDocumentsModalProps {
  assessmentId: string;
  assessmentName: string;
  onClose: () => void;
  /**
   * When set, the modal is the document step of assessment creation: it shows a
   * "Start analysis" action, and any dismissal (button, ✕, Escape, backdrop)
   * calls this to trigger the agents — so the first run sees the uploaded docs.
   * Omit for the standalone (post-creation) Docs view.
   */
  onStartAnalysis?: () => void;
}

// What the file picker accepts; mirrors the backend's allowlist.
const ACCEPT = '.pdf,.txt,.md,.markdown,.docx,image/*';

const introCss = css({
  marginBottom: spacing.sm,
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

const noticeCss = css({
  padding: spacing.sm,
  marginBottom: spacing.sm,
  background: colors.infoLight,
  borderRadius: radius.md,
  color: colors.text,
  fontSize: fontSizes.sm,
});

const createdCss = css({
  display: 'flex',
  alignItems: 'baseline',
  gap: spacing.xs,
  padding: spacing.sm,
  marginBottom: spacing.sm,
  background: colors.successLight,
  borderRadius: radius.md,
  color: colors.text,
  fontSize: fontSizes.sm,
});

const errorCss = css({
  padding: spacing.xs,
  marginBottom: spacing.sm,
  background: colors.errorLight,
  borderRadius: radius.md,
  color: colors.error,
  fontSize: fontSizes.sm,
});

const toolbarCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  marginBottom: spacing.sm,
});

const hintCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const listCss = css({
  display: 'flex',
  flexDirection: 'column',
  gap: '6px',
  listStyle: 'none',
  margin: 0,
  padding: 0,
});

const itemCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  padding: `${spacing.xs} ${spacing.sm}`,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.md,
});

const nameCss = css({
  flex: 1,
  minWidth: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: '2px',
});

const linkCss = css({
  fontSize: fontSizes.sm,
  fontWeight: 600,
  color: colors.text,
  textDecoration: 'none',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  '&:hover': { color: colors.primaryText, textDecoration: 'underline' },
});

const metaCss = css({
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const emptyCss = css({
  padding: `${spacing.md} 0`,
  textAlign: 'center',
  color: colors.textLight,
  fontSize: fontSizes.sm,
});

const footerCss = css({
  display: 'flex',
  justifyContent: 'flex-end',
  gap: spacing.xs,
  marginTop: spacing.md,
  paddingTop: spacing.sm,
  borderTop: `1px solid ${colors.borderLight}`,
});

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface DocumentRowProps {
  assessmentId: string;
  document: AssessmentDocument;
  onDelete: (id: string) => void;
}

const DocumentRow = ({ assessmentId, document, onDelete }: DocumentRowProps) => (
  <li css={itemCss}>
    <span aria-hidden="true">{document.kind === 'image' ? '🖼️' : '📄'}</span>
    <span css={nameCss}>
      <a
        css={linkCss}
        href={documentApi.contentUrl(assessmentId, document.id)}
        target="_blank"
        rel="noreferrer"
        title={document.filename}
      >
        {document.filename}
      </a>
      <span css={metaCss}>
        {document.kind === 'image' ? 'Image' : 'Text'} · {formatSize(document.size)}
      </span>
    </span>
    <Button
      variant="danger"
      size="sm"
      onClick={() => onDelete(document.id)}
      aria-label={`Delete ${document.filename}`}
      title="Delete"
    >
      <span aria-hidden="true">✕</span>
    </Button>
  </li>
);

export const AssessmentDocumentsModal = ({
  assessmentId,
  assessmentName,
  onClose,
  onStartAnalysis,
}: AssessmentDocumentsModalProps) => {
  const { documents, enabled, isLoading, error, uploading, upload, remove } =
    useAssessmentDocuments(assessmentId);
  const inputRef = useRef<HTMLInputElement>(null);
  const creating = onStartAnalysis !== undefined;
  // Set once the analysis is being kicked off, to show a loading state until the
  // parent triggers the agents and swaps this modal out.
  const [starting, setStarting] = useState(false);

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    // Clear the input so re-selecting the same file fires change again.
    event.target.value = '';
    if (files.length > 0) void upload(files);
  };

  // In the creation step, every dismissal proceeds to the agents (so a new
  // assessment never lands with no run), but never mid-upload — an in-flight
  // file must be persisted before the agents read the document set — and never
  // twice while a trigger is already in flight.
  const handleDismiss = () => {
    if (!creating) {
      onClose();
      return;
    }
    if (!uploading && !starting) {
      setStarting(true);
      onStartAnalysis();
    }
  };

  return (
    <Modal title="Architecture documents" onClose={handleDismiss} size="md">
      {creating && (
        <p css={createdCss}>
          <span aria-hidden="true">✓</span> Assessment <strong>{assessmentName}</strong>{' '}
          created. Attach architecture documents below (optional), then start the analysis.
        </p>
      )}

      <p css={introCss}>
        Upload documentation of the architecture for <strong>{assessmentName}</strong>{' '}
        (PDF, TXT, MD, DOCX, or images). The agents read these as extra context when
        answering this assessment&apos;s questions.
        {creating &&
          ' Add them now so the first agent run uses them — you can add more later.'}
      </p>

      {!enabled && !isLoading && (
        <p css={noticeCss}>
          Document uploads aren&apos;t available in this environment. They work in the
          deployed app, where a storage Volume is configured.
        </p>
      )}

      {error && <p css={errorCss}>{error}</p>}

      {enabled && (
        <div css={toolbarCss}>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            onChange={handleFiles}
            hidden
          />
          <Button
            variant="primary"
            onClick={() => inputRef.current?.click()}
            disabled={uploading || starting}
          >
            {uploading ? 'Uploading…' : 'Upload files'}
          </Button>
          <span css={hintCss}>PDF, TXT, MD, DOCX, or images · up to 25 MB each</span>
        </div>
      )}

      {isLoading ? (
        <p css={emptyCss}>Loading…</p>
      ) : documents.length === 0 ? (
        <p css={emptyCss}>No documents uploaded yet.</p>
      ) : (
        <ul css={listCss}>
          {documents.map((document) => (
            <DocumentRow
              key={document.id}
              assessmentId={assessmentId}
              document={document}
              onDelete={remove}
            />
          ))}
        </ul>
      )}

      {creating && (
        <div css={footerCss}>
          <Button
            variant="primary"
            onClick={handleDismiss}
            disabled={uploading || starting}
          >
            {starting
              ? 'Starting analysis…'
              : uploading
                ? 'Uploading…'
                : documents.length > 0
                  ? 'Start analysis'
                  : 'Skip & start analysis'}
          </Button>
        </div>
      )}
    </Modal>
  );
};
