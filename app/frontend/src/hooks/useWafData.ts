/**
 * Loads the WAF question set.
 */

import { useEffect, useState } from 'react';
import { loadWafData } from '@/data/loadWafData';
import type { WafData } from '@/data/loadWafData';

export interface WafDataState {
  data: WafData | null;
  isLoading: boolean;
  error: Error | null;
}

export function useWafData(): WafDataState {
  const [state, setState] = useState<WafDataState>({
    data: null,
    isLoading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    loadWafData()
      .then((data) => {
        if (cancelled) return;
        setState({ data, isLoading: false, error: null });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          data: null,
          isLoading: false,
          error: error instanceof Error ? error : new Error(String(error)),
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
