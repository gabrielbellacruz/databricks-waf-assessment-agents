/**
 * Loads the latest implementation backlog for an assessment and polls while a
 * run is active.
 *
 * The backlog agent runs asynchronously in the backend (no Databricks Job), so
 * this hook fetches the latest run + tasks and, while the run is queued or
 * running, re-polls until it finishes. `generate` triggers a new run and restarts
 * the poll loop (see the reload-key note, mirroring useAgentFindings).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { backlogApi } from '@/store/api';
import type { BacklogContext } from '@/core/backlogContext';
import type { BacklogRun, BacklogTask } from '@/types/waf';

const POLL_MS = 4000;
const ACTIVE = new Set(['queued', 'running']);

export interface BacklogState {
  run: BacklogRun | null;
  tasks: BacklogTask[];
  isLoading: boolean;
  /** False once a trigger reports the agent can't run here (local dev). */
  enabled: boolean;
  /** Trigger a new backlog run for this assessment, then follow it to completion. */
  generate: (context: BacklogContext) => Promise<void>;
}

export function useBacklog(assessmentId: string | null): BacklogState {
  const [run, setRun] = useState<BacklogRun | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Optimistic: assume available until a trigger tells us otherwise.
  const [enabled, setEnabled] = useState(true);
  // Bumped by generate() to restart the fetch/poll loop below - the effect polls
  // only until a run finishes, so a re-triggered run needs the loop kicked off
  // again to be followed to completion.
  const [reloadKey, setReloadKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const generate = useCallback(
    async (context: BacklogContext) => {
      if (!assessmentId) return;
      const response = await backlogApi.run(assessmentId, context);
      // A 202 {"enabled": false} means the backend can't reach the model (local
      // dev); anything else is a real queued run.
      try {
        const body: unknown = await response.clone().json();
        if (
          typeof body === 'object' &&
          body !== null &&
          'enabled' in body &&
          body.enabled === false
        ) {
          setEnabled(false);
          return;
        }
      } catch {
        // No/!JSON body - treat as a normal trigger.
      }
      setEnabled(true);
      setReloadKey((key) => key + 1);
    },
    [assessmentId],
  );

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      if (cancelled || !assessmentId) return;
      try {
        const response = await backlogApi.get(assessmentId);
        if (cancelled) return;
        setRun(response.run);
        setIsLoading(false);
        if (response.run && ACTIVE.has(response.run.status)) {
          timer.current = setTimeout(tick, POLL_MS);
        }
      } catch {
        if (!cancelled) setIsLoading(false);
      }
    };

    if (!assessmentId) {
      setRun(null);
      setIsLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setIsLoading(true);
    void tick();

    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [assessmentId, reloadKey]);

  return { run, tasks: run?.tasks ?? [], isLoading, enabled, generate };
}
