import { useEffect, useState } from 'react';
import { getAnalysis, getTranscript } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useProcessingStatus } from '../hooks/useProcessingStatus';
import type { AudioResponseResponse, InterviewAnalysisResponse, TranscriptResponse } from '../api/types';
import { AnalysisCard } from './AnalysisCard';
import { ProcessingStatusCard } from './ProcessingStatusCard';
import { TranscriptCard } from './TranscriptCard';

export function ResponseCard({ response }: { response: AudioResponseResponse }) {
  const { token } = useAuth();
  const { status, pollError } = useProcessingStatus(response.id, response.status, token);

  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [analysis, setAnalysis] = useState<InterviewAnalysisResponse | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);
  const [resultsError, setResultsError] = useState(false);

  useEffect(() => {
    if (status !== 'completed' || !token) return;

    let cancelled = false;
    setLoadingResults(true);
    setResultsError(false);

    Promise.all([getTranscript(response.id, token), getAnalysis(response.id, token)])
      .then(([transcriptData, analysisData]) => {
        if (cancelled) return;
        setTranscript(transcriptData);
        setAnalysis(analysisData);
      })
      .catch(() => {
        if (cancelled) return;
        setResultsError(true);
      })
      .finally(() => {
        if (cancelled) return;
        setLoadingResults(false);
      });

    return () => {
      cancelled = true;
    };
  }, [status, response.id, token]);

  return (
    <div className="response-card">
      <ProcessingStatusCard status={status} pollError={pollError} />

      {status === 'completed' && loadingResults && <p>Loading transcript and analysis…</p>}
      {status === 'completed' && resultsError && (
        <p className="status-warning">
          Unable to load the transcript and analysis right now. Please refresh the page.
        </p>
      )}

      {transcript && <TranscriptCard transcript={transcript} />}
      {analysis && <AnalysisCard analysis={analysis} />}
    </div>
  );
}
