import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ProcessingStatusCard } from './ProcessingStatusCard';

describe('ProcessingStatusCard', () => {
  it('renders the uploaded state', () => {
    render(<ProcessingStatusCard status="uploaded" />);
    expect(screen.getByText('Uploaded')).toBeInTheDocument();
    expect(screen.getByText(/waiting to be processed/i)).toBeInTheDocument();
  });

  it('renders the processing state with a spinner', () => {
    render(<ProcessingStatusCard status="processing" />);
    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByLabelText('Processing')).toBeInTheDocument();
  });

  it('renders the completed state', () => {
    render(<ProcessingStatusCard status="completed" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText(/transcript and analysis are ready/i)).toBeInTheDocument();
  });

  it('renders the failed state with retry guidance and no raw error message', () => {
    render(<ProcessingStatusCard status="failed" />);
    expect(screen.getByText('Processing failed')).toBeInTheDocument();
    expect(screen.getByText(/try uploading the recording again/i)).toBeInTheDocument();
  });

  it('shows a generic message when polling fails, without crashing', () => {
    render(<ProcessingStatusCard status="processing" pollError />);
    expect(screen.getByText(/unable to check the latest status/i)).toBeInTheDocument();
  });
});
