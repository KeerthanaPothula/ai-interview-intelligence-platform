import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { VoiceAnalysisResponse } from '../api/types';
import { VoiceAnalyticsCard } from './VoiceAnalyticsCard';

const BASE_VOICE: VoiceAnalysisResponse = {
  id: '11111111-0000-0000-0000-000000000001',
  audio_response_id: '22222222-0000-0000-0000-000000000001',
  speaking_rate: 135.5,
  average_pause_duration: 0.8,
  total_pause_time: 4.2,
  long_pause_count: 1,
  filler_word_count: 3,
  energy_consistency: 0.74,
  confidence_score: 77,
  created_at: '2026-06-18T10:00:00Z',
};

describe('VoiceAnalyticsCard', () => {
  it('renders the card heading', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    expect(screen.getByText('Voice Analytics')).toBeTruthy();
  });

  it('renders the confidence badge with score', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    const badge = screen.getByTestId('confidence-badge');
    expect(badge.textContent).toContain('77');
  });

  it('renders "Moderate" label for mid-range confidence (55–79)', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    const badge = screen.getByTestId('confidence-badge');
    expect(badge.textContent).toContain('Moderate');
  });

  it('renders "High Confidence" for score >= 80', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={{ ...BASE_VOICE, confidence_score: 85 }} />);
    expect(screen.getByTestId('confidence-badge').textContent).toContain('High Confidence');
  });

  it('renders "Needs Work" for score < 55', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={{ ...BASE_VOICE, confidence_score: 40 }} />);
    expect(screen.getByTestId('confidence-badge').textContent).toContain('Needs Work');
  });

  it('renders speaking rate metric', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    expect(screen.getByText('Speaking Rate')).toBeTruthy();
    expect(screen.getByText('136 WPM')).toBeTruthy();
  });

  it('renders filler word count', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    expect(screen.getByText('Filler Words')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
  });

  it('renders energy consistency as percentage', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    expect(screen.getByText('74%')).toBeTruthy();
  });

  it('renders dashes for null metrics', () => {
    const nullVoice: VoiceAnalysisResponse = {
      ...BASE_VOICE,
      speaking_rate: null,
      filler_word_count: null,
      energy_consistency: null,
      confidence_score: null,
    };
    render(<VoiceAnalyticsCard voiceAnalysis={nullVoice} />);
    // No badge when confidence_score is null
    expect(screen.queryByTestId('confidence-badge')).toBeNull();
    // Metrics show dashes
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('has testid on the card root', () => {
    render(<VoiceAnalyticsCard voiceAnalysis={BASE_VOICE} />);
    expect(screen.getByTestId('voice-analytics-card')).toBeTruthy();
  });
});
