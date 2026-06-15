import type { ResponseStatus } from '../api/types';

interface ProcessingStatusCardProps {
  status: ResponseStatus;
  pollError?: boolean;
}

const STATUS_CONFIG: Record<
  ResponseStatus,
  { label: string; description: string; className: string }
> = {
  uploaded: {
    label: 'Uploaded',
    description: 'Your recording was uploaded and is waiting to be processed.',
    className: 'status-neutral',
  },
  processing: {
    label: 'Processing',
    description:
      'We are transcribing and evaluating your response. This usually takes a minute.',
    className: 'status-info',
  },
  completed: {
    label: 'Completed',
    description: 'Processing is complete. Your transcript and analysis are ready below.',
    className: 'status-success',
  },
  failed: {
    label: 'Processing failed',
    description:
      'Something went wrong while processing this response. Please try uploading the recording again.',
    className: 'status-error',
  },
};

export function ProcessingStatusCard({ status, pollError }: ProcessingStatusCardProps) {
  const config = STATUS_CONFIG[status];

  return (
    <div className={`processing-status-card ${config.className}`} data-testid="processing-status-card">
      <div className="status-row">
        <span className="status-badge">{config.label}</span>
        {status === 'processing' && <span className="spinner" aria-label="Processing" />}
      </div>
      <p>{config.description}</p>
      {pollError && (
        <p className="status-warning">
          Unable to check the latest status right now. We&apos;ll keep trying.
        </p>
      )}
    </div>
  );
}
