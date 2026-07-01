import { useEffect, useState } from 'react';
import { getAnalysis, getTranscript, getVoiceAnalysis } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useProcessingStatus } from '../hooks/useProcessingStatus';
import type {
  AudioResponseResponse,
  InterviewAnalysisResponse,
  TranscriptResponse,
  VoiceAnalysisResponse,
} from '../api/types';
import { AnalysisCard } from './AnalysisCard';
import { ProcessingStatusCard } from './ProcessingStatusCard';
import { ResponseResultsSkeleton } from './Skeleton';
import { TranscriptCard } from './TranscriptCard';
import { VoiceAnalyticsCard } from './VoiceAnalyticsCard';

export function ResponseCard({ response }: { response: AudioResponseResponse }) {
  const { token } = useAuth();
  const { status, pollError } = useProcessingStatus(response.id, response.status, token);

  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [analysis, setAnalysis] = useState<InterviewAnalysisResponse | null>(null);
  const [voiceAnalysis, setVoiceAnalysis] = useState<VoiceAnalysisResponse | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);
  const [resultsError, setResultsError] = useState(false);

  useEffect(() => {
    if (status !== 'completed' || !token) return;

    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- guarded by `cancelled`, standard data-fetching pattern
    setLoadingResults(true);
    setResultsError(false);

    Promise.all([
      getTranscript(response.id, token),
      getAnalysis(response.id, token),
      getVoiceAnalysis(response.id, token).catch(() => null),
    ])
      .then(([transcriptData, analysisData, voiceData]) => {
        if (cancelled) return;
        setTranscript(transcriptData);
        setAnalysis(analysisData);
        setVoiceAnalysis(voiceData);
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

      {status === 'completed' && loadingResults && <ResponseResultsSkeleton />}
      {status === 'completed' && resultsError && (
        <p className="status-warning" role="alert">
          Unable to load the transcript and analysis right now. Please refresh the page.
        </p>
      )}

      {voiceAnalysis && <VoiceAnalyticsCard voiceAnalysis={voiceAnalysis} />}
      {transcript && <TranscriptCard transcript={transcript} />}
      {analysis && <AnalysisCard analysis={analysis} />}
    </div>
  );
}
