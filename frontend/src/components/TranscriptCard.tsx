import type { TranscriptResponse } from '../api/types';

function formatDuration(seconds: number | null): string {
  if (seconds === null) return 'Unknown';
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

export function TranscriptCard({ transcript }: { transcript: TranscriptResponse }) {
  return (
    <div className="transcript-card" data-testid="transcript-card">
      <h3>Transcript</h3>
      <dl className="meta-grid">
        <div className="meta-item">
          <dt>Language</dt>
          <dd>{transcript.language ?? 'Unknown'}</dd>
        </div>
        <div className="meta-item">
          <dt>Word count</dt>
          <dd>{transcript.word_count}</dd>
        </div>
        <div className="meta-item">
          <dt>Duration</dt>
          <dd>{formatDuration(transcript.duration_seconds)}</dd>
        </div>
      </dl>
      <p className="transcript-text">{transcript.text || 'No speech was detected in this recording.'}</p>
    </div>
  );
}
