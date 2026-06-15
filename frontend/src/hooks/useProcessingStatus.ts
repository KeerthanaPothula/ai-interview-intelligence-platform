import { useEffect, useState } from 'react';
import { getProcessingStatus } from '../api/client';
import type { ResponseStatus } from '../api/types';

export const POLL_INTERVAL_MS = 3000;

const TERMINAL_STATUSES: ResponseStatus[] = ['completed', 'failed'];

export interface ProcessingStatusState {
  status: ResponseStatus;
  transcriptId: string | null;
  analysisId: string | null;
  errorMessage: string | null;
  pollError: boolean;
}

/**
 * Polls GET /responses/{responseId}/processing-status every
 * POLL_INTERVAL_MS until status reaches a terminal state
 * ('completed' or 'failed'), then stops.
 */
export function useProcessingStatus(
  responseId: string,
  initialStatus: ResponseStatus,
  token: string | null,
): ProcessingStatusState {
  const [state, setState] = useState<ProcessingStatusState>({
    status: initialStatus,
    transcriptId: null,
    analysisId: null,
    errorMessage: null,
    pollError: false,
  });

  useEffect(() => {
    if (!token || TERMINAL_STATUSES.includes(state.status)) {
      return;
    }

    let cancelled = false;

    const interval = setInterval(() => {
      getProcessingStatus(responseId, token)
        .then((data) => {
          if (cancelled) return;
          setState({
            status: data.status,
            transcriptId: data.transcript_id,
            analysisId: data.analysis_id,
            errorMessage: data.error_message,
            pollError: false,
          });
        })
        .catch(() => {
          if (cancelled) return;
          setState((prev) => ({ ...prev, pollError: true }));
        });
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [responseId, token, state.status]);

  return state;
}
