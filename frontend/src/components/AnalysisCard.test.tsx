import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnalysisCard } from './AnalysisCard';
import type { InterviewAnalysisResponse } from '../api/types';

const baseAnalysis: InterviewAnalysisResponse = {
  id: 'a-1',
  audio_response_id: 'r-1',
  transcript_id: 't-1',
  overall_score: '7.5',
  communication_score: '8.0',
  technical_score: '7.0',
  problem_solving_score: '6.5',
  confidence_score: '8.5',
  strengths: '["Clear structure", "Good technical depth"]',
  weaknesses: '["Could be more concise"]',
  detailed_feedback: 'Overall a strong answer with room to tighten the delivery.',
  model_used: 'gemini-2.0-flash',
  created_at: '2026-06-01T00:00:00Z',
};

describe('AnalysisCard', () => {
  it('renders all five scores', () => {
    render(<AnalysisCard analysis={baseAnalysis} />);
    expect(screen.getByText('Overall Score')).toBeInTheDocument();
    expect(screen.getByText('7.5 / 10')).toBeInTheDocument();
    expect(screen.getByText('Communication Score')).toBeInTheDocument();
    expect(screen.getByText('8.0 / 10')).toBeInTheDocument();
    expect(screen.getByText('Technical Score')).toBeInTheDocument();
    expect(screen.getByText('7.0 / 10')).toBeInTheDocument();
    expect(screen.getByText('Problem Solving Score')).toBeInTheDocument();
    expect(screen.getByText('6.5 / 10')).toBeInTheDocument();
    expect(screen.getByText('Confidence Score')).toBeInTheDocument();
    expect(screen.getByText('8.5 / 10')).toBeInTheDocument();
  });

  it('parses strengths and weaknesses JSON into list items', () => {
    render(<AnalysisCard analysis={baseAnalysis} />);
    expect(screen.getByText('Clear structure')).toBeInTheDocument();
    expect(screen.getByText('Good technical depth')).toBeInTheDocument();
    expect(screen.getByText('Could be more concise')).toBeInTheDocument();
  });

  it('renders detailed feedback', () => {
    render(<AnalysisCard analysis={baseAnalysis} />);
    expect(screen.getByText(baseAnalysis.detailed_feedback as string)).toBeInTheDocument();
  });

  it('handles null strengths, weaknesses, and detailed feedback gracefully', () => {
    render(
      <AnalysisCard
        analysis={{ ...baseAnalysis, strengths: null, weaknesses: null, detailed_feedback: null }}
      />,
    );
    expect(screen.queryByText('Strengths')).not.toBeInTheDocument();
    expect(screen.queryByText('Weaknesses')).not.toBeInTheDocument();
    expect(screen.queryByText('Detailed Feedback')).not.toBeInTheDocument();
  });
});
