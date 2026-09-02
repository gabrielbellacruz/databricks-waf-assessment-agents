/**
 * Loads and mutates the architecture documents attached to an assessment.
 *
 * Documents are their own server-side resource (stored in a UC Volume, read by
 * the agents), so this hook keeps them out of the assessment store: it fetches
 * the list, exposes `enabled` (false when the deployment can't store files, e.g.
 * local dev without a profile), and wraps upload/delete with a refresh.
 */

import { useCallback, useEffect, useState } from 'react';
import { documentApi } from '@/store/api';
import type { AssessmentDocument } from '@/types/waf';

export interface AssessmentDocumentsState {
  documents: AssessmentDocument[];
  /** Whether uploading is available in this deployment. */
  enabled: boolean;
  isLoading: boolean;
  /** Last upload/delete error, for inline display. */
  error: string | null;
  uploading: boolean;
  upload: (files: File[]) => Promise<void>;
  remove: (documentId: string) => Promise<void>;
}

export function useAssessmentDocuments(
  assessmentId: string | null,
): AssessmentDocumentsState {
  const [documents, setDocuments] = useState<AssessmentDocument[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!assessmentId) return;
    const response = await documentApi.list(assessmentId);
    setEnabled(response.enabled);
    setDocuments(response.documents);
  }, [assessmentId]);

  useEffect(() => {
    let cancelled = false;
    if (!assessmentId) {
      setDocuments([]);
      setEnabled(false);
      setIsLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setIsLoading(true);
    documentApi
      .list(assessmentId)
      .then((response) => {
        if (cancelled) return;
        setEnabled(response.enabled);
        setDocuments(response.documents);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load documents.');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assessmentId]);

  const upload = useCallback(
    async (files: File[]) => {
      if (!assessmentId || files.length === 0) return;
      setUploading(true);
      setError(null);
      try {
        // Sequential: uploads share one Volume and are typically few.
        for (const file of files) {
          await documentApi.upload(assessmentId, file);
        }
        await load();
      } catch {
        setError('Upload failed. Check the file type and size (max 25 MB).');
      } finally {
        setUploading(false);
      }
    },
    [assessmentId, load],
  );

  const remove = useCallback(
    async (documentId: string) => {
      if (!assessmentId) return;
      setError(null);
      // Optimistic: drop it locally, then reconcile against the server.
      setDocuments((docs) => docs.filter((d) => d.id !== documentId));
      try {
        await documentApi.remove(assessmentId, documentId);
      } catch {
        setError('Could not delete the document.');
        await load();
      }
    },
    [assessmentId, load],
  );

  return { documents, enabled, isLoading, error, uploading, upload, remove };
}
