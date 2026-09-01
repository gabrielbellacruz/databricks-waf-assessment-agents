/**
 * Per-question free-text notes.
 *
 * A collapsible textarea so a customer can jot context against a question.
 * Empty and untouched, it shows only a subtle "Add note" affordance; once a
 * note exists (or the affordance is opened) the textarea is shown.
 *
 * Saving mirrors the answer status: an edit is persisted on blur, and a
 * debounced save catches edits made without blurring (e.g. keyboard nav that
 * unmounts the field). A save is skipped when the value has not changed since
 * the last persisted value, so redundant writes are avoided.
 */

import { css } from '@emotion/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { colors, fontSizes, radius, spacing, transitions } from '@/styles/theme';

/** Delay before an in-progress edit is auto-saved, in milliseconds. */
const DEBOUNCE_MS = 700;

export interface QuestionNotesProps {
  /** The persisted note for this question, or an empty string when none. */
  note: string;
  /** Persist a new note value for this question. */
  onChange: (note: string) => void;
}

const wrapperCss = css({
  marginTop: spacing.md,
});

const addButtonCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  padding: '6px 12px',
  background: colors.background,
  border: `1px dashed ${colors.border}`,
  borderRadius: radius.full,
  fontSize: fontSizes.sm,
  fontWeight: 500,
  color: colors.textLight,
  transition: `all ${transitions.fast}`,

  '&:hover': {
    borderColor: colors.textLight,
    color: colors.text,
  },
});

const labelCss = css({
  display: 'block',
  fontSize: fontSizes.sm,
  fontWeight: 600,
  marginBottom: spacing.xs,
});

const textareaCss = css({
  width: '100%',
  minHeight: '96px',
  padding: spacing.sm,
  background: colors.backgroundLight,
  border: `1px solid ${colors.border}`,
  borderRadius: radius.md,
  fontSize: fontSizes.sm,
  fontFamily: 'inherit',
  color: colors.text,
  resize: 'vertical',
  transition: `border-color ${transitions.fast}`,

  '&::placeholder': {
    color: colors.textLight,
  },
  '&:focus': {
    outline: 'none',
    borderColor: colors.primaryText,
  },
});

export const QuestionNotes = ({ note, onChange }: QuestionNotesProps) => {
  const [draft, setDraft] = useState(note);
  const [expanded, setExpanded] = useState(note.trim() !== '');

  // The last value handed to onChange, so we don't re-persist an unchanged note.
  const savedRef = useRef(note);
  // The latest draft, read from the unmount cleanup to flush a pending edit.
  const draftRef = useRef(note);
  const timerRef = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const save = useCallback(
    (value: string) => {
      if (value === savedRef.current) return;
      savedRef.current = value;
      onChange(value);
    },
    [onChange],
  );

  // Flush any pending edit when the field unmounts (e.g. navigating questions).
  useEffect(
    () => () => {
      clearTimer();
      save(draftRef.current);
    },
    [clearTimer, save],
  );

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    setDraft(value);
    draftRef.current = value;
    clearTimer();
    timerRef.current = window.setTimeout(() => save(value), DEBOUNCE_MS);
  };

  const handleBlur = () => {
    clearTimer();
    save(draft);
  };

  if (!expanded) {
    return (
      <div css={wrapperCss}>
        <button type="button" css={addButtonCss} onClick={() => setExpanded(true)}>
          <span aria-hidden="true">＋</span> Add note
        </button>
      </div>
    );
  }

  return (
    <div css={wrapperCss}>
      <label css={labelCss} htmlFor="question-note">
        Notes
      </label>
      <textarea
        id="question-note"
        css={textareaCss}
        value={draft}
        placeholder="Add context, decisions, or follow-ups for this question…"
        onChange={handleChange}
        onBlur={handleBlur}
      />
    </div>
  );
};
