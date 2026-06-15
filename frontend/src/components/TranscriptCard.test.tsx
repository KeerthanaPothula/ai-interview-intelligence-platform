import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TranscriptCard } from './TranscriptCard';
import type { TranscriptResponse } from '../api/types';

const baseTranscript: TranscriptResponse = {
  id: 't-1',
  audio_response_id: 'r-1',
  text: 'This is my answer to the question.',
  language: 'en',
  duration_seconds: 125,
  word_count: 8,
  created_at: '2026-06-01T00:00:00Z',
};

describe('TranscriptCard', () => {
  it('renders transcript text, language, word count, and formatted duration', () => {
    render(<TranscriptCard transcript={baseTranscript} />);
    expect(screen.getByText(baseTranscript.text)).toBeInTheDocument();
    expect(screen.getByText('en')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('2m 5s')).toBeInTheDocument();
  });

  it('shows fallbacks for unknown language, unknown duration, and empty text', () => {
    render(
      <TranscriptCard
        transcript={{ ...baseTranscript, language: null, duration_seconds: null, text: '' }}
      />,
    );
    expect(screen.getAllByText('Unknown')).toHaveLength(2);
    expect(screen.getByText(/no speech was detected/i)).toBeInTheDocument();
  });
});
