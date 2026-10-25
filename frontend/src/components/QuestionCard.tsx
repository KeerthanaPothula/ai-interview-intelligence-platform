import { useRef, useState } from 'react';
import { ApiError, submitTextAnswer, uploadResponse } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useFeatures } from '../context/FeaturesContext.shared';
import type { AudioResponseResponse, QuestionResponse, TextAnswerResponse } from '../api/types';
import { ResponseCard } from './ResponseCard';

interface QuestionCardProps {
  question: QuestionResponse;
  sessionId: string;
  responses: AudioResponseResponse[];
  onUploaded: (response: AudioResponseResponse) => void;
  answer?: TextAnswerResponse;
  onAnswerSubmitted: (answer: TextAnswerResponse) => void;
  onNext?: () => void;
}

export function QuestionCard({ question, sessionId, responses, onUploaded, answer, onAnswerSubmitted, onNext }: QuestionCardProps) {
  const { token } = useAuth();
  const { audioEnabled } = useFeatures();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answerText, setAnswerText] = useState(answer?.answer_text ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);

  async function handleSubmitAnswer() {
    if (!token || !answerText.trim() || submitting || answer) return;
    setSubmitting(true);
    setAnswerError(null);
    try {
      onAnswerSubmitted(await submitTextAnswer(sessionId, question.id, answerText, token));
    } catch (err) {
      setAnswerError(err instanceof ApiError ? err.message : 'Unable to submit your answer. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file || !token) return;

    setUploading(true);
    setError(null);
    try {
      const response = await uploadResponse(sessionId, question.id, file, token);
      onUploaded(response);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="question-card" id={`question-${question.id}`}>
      <div className="question-header">
        <span className="question-order">Q{question.sequence_order}</span>
        {question.category && <span className="question-category">{question.category}</span>}
      </div>
      <p className="question-body">{question.body}</p>

      <div className="text-answer-section">
        <label htmlFor={`answer-${question.id}`}>Your answer</label>
        <textarea
          id={`answer-${question.id}`}
          value={answer?.answer_text ?? answerText}
          onChange={(event) => setAnswerText(event.target.value)}
          placeholder="Write your answer here…"
          rows={5}
          maxLength={20000}
          disabled={Boolean(answer) || submitting}
          aria-describedby={answerError ? `answer-error-${question.id}` : undefined}
        />
        {!answer ? (
          <button className="btn btn-primary" type="button" onClick={handleSubmitAnswer} disabled={!answerText.trim() || submitting} aria-busy={submitting}>
            {submitting ? <><span className="spinner" aria-hidden="true" /> Submitting…</> : 'Submit Answer'}
          </button>
        ) : (
          <p className="answer-saved" role="status">Answer saved</p>
        )}
        {answerError && <p id={`answer-error-${question.id}`} className="status-error-text" role="alert">{answerError}</p>}
        {answer?.overall_score != null && (
          <div className="answer-evaluation" aria-label="AI evaluation">
            <strong>Score: {answer.overall_score.toFixed(1)} / 10</strong>
            {answer.detailed_feedback && <p>{answer.detailed_feedback}</p>}
            {answer.strengths?.length ? <><h4>Strengths</h4><ul>{answer.strengths.map((item) => <li key={item}>{item}</li>)}</ul></> : null}
            {answer.weaknesses?.length ? <><h4>Areas to improve</h4><ul>{answer.weaknesses.map((item) => <li key={item}>{item}</li>)}</ul></> : null}
          </div>
        )}
        {answer && onNext && <button className="btn btn-ghost btn-sm" type="button" onClick={onNext}>Next Question →</button>}
      </div>

      {audioEnabled ? (
        <>
          <div className="upload-controls">
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              disabled={uploading}
              aria-label={`Audio recording for question ${question.sequence_order}`}
            />
            <button type="button" onClick={handleUpload} disabled={uploading}>
              {uploading ? 'Uploading…' : 'Upload Recording'}
            </button>
          </div>
          {error && (
            <p className="status-error-text" role="alert">
              {error}
            </p>
          )}
        </>
      ) : (
        <p className="audio-disabled-notice">
          Audio upload is not available in this deployment. Use the live interview
          or text-based practice modes instead.
        </p>
      )}

      {responses.length > 0 && (
        <div className="responses-list">
          {responses.map((response) => (
            <ResponseCard key={response.id} response={response} />
          ))}
        </div>
      )}
    </div>
  );
}
