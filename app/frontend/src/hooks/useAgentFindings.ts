/**
 * Loads agent findings for one assessment layer and polls while a run is active.
 *
 * The agent runs asynchronously as a Databricks Job, so this hook fetches the
 * latest run + findings, and - while the run is queued or running - re-polls
 * until it finishes. Returns an empty result when no agent has run (e.g. the
 * layer has no agent, or the deployment can't trigger one).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { agentApi } from '@/store/api';
import type { AgentFinding, AgentRun } from '@/types/waf';

const POLL_MS = 4000;
const ACTIVE = new Set(['queued', 'running']);

export interface AgentFindingsState {
  run: AgentRun | null;
  findings: Record<string, AgentFinding>;
  isLoading: boolean;
  /** Re-trigger the agent for this layer (used by a Refresh action). */
  refresh: () => Promise<void>;
}

export function useAgentFindings(
  assessmentId: string | null,
  layer: string,
): AgentFindingsState {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [findings, setFindings] = useState<Record<string, AgentFinding>>({});
  const [isLoading, setIsLoading] = useState(true);
  // Bumped by refresh() to restart the fetch/poll loop below - the effect polls
  // only until a run finishes, so a re-triggered run needs the loop kicked off
  // again to be followed to completion.
  const [reloadKey, setReloadKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    if (!assessmentId) return;
    // Trigger (or reuse) a run for this layer, then restart the poll loop so
    // the new run is followed even if a previous run had already finished.
    await agentApi.run(assessmentId, layer);
    setReloadKey((key) => key + 1);
  }, [assessmentId, layer]);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      if (cancelled || !assessmentId || !layer) return;
      try {
        const response = await agentApi.getFindings(assessmentId, layer);
        if (cancelled) return;
        setRun(response.run);
        setFindings(response.findings);
        setIsLoading(false);
        if (response.run && ACTIVE.has(response.run.status)) {
          timer.current = setTimeout(tick, POLL_MS);
        }
      } catch {
        if (!cancelled) setIsLoading(false);
      }
    };

    if (!assessmentId || !layer) {
      setRun(null);
      setFindings({});
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
  }, [assessmentId, layer, reloadKey]);

  return { run, findings, isLoading, refresh };
}
