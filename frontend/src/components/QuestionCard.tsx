import { useRef, useState } from 'react';
import { ApiError, uploadResponse } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { AudioResponseResponse, QuestionResponse } from '../api/types';
import { ResponseCard } from './ResponseCard';

interface QuestionCardProps {
  question: QuestionResponse;
  sessionId: string;
  responses: AudioResponseResponse[];
  onUploaded: (response: AudioResponseResponse) => void;
}

export function QuestionCard({ question, sessionId, responses, onUploaded }: QuestionCardProps) {
  const { token } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    <div className="question-card">
      <div className="question-header">
        <span className="question-order">Q{question.sequence_order}</span>
        {question.category && <span className="question-category">{question.category}</span>}
      </div>
      <p className="question-body">{question.body}</p>

      <div className="upload-controls">
        <input ref={fileInputRef} type="file" accept="audio/*" disabled={uploading} />
        <button type="button" onClick={handleUpload} disabled={uploading}>
          {uploading ? 'Uploading…' : 'Upload Recording'}
        </button>
      </div>
      {error && <p className="status-error-text">{error}</p>}

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
