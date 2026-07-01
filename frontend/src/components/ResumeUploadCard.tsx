import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, getCurrentResume, uploadResume } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { ResumeDocumentResponse } from '../api/types';

export function ResumeUploadCard() {
  const { token } = useAuth();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [resume, setResume] = useState<ResumeDocumentResponse | null>(null);
  const [checking, setChecking] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadResume = useCallback(() => {
    if (!token) return;
    setChecking(true);
    getCurrentResume(token)
      .then(setResume)
      .catch(() => setResume(null))
      .finally(() => setChecking(false));
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    loadResume();
  }, [loadResume]);

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file || !token) return;

    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadResume(file, token);
      setResume(uploaded);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      showToast('Resume uploaded.', 'success');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Resume upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  if (checking) return null;

  return (
    <section className="resume-upload-card">
      <h2>Resume</h2>
      {resume ? (
        <p className="resume-status">
          Current resume: <strong>{resume.filename}</strong> ({resume.chunk_count} chunks indexed)
        </p>
      ) : (
        <p className="resume-status">No resume uploaded yet. Upload one to personalize generated questions.</p>
      )}
      <div className="upload-controls">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          disabled={uploading}
          aria-label="Resume file"
        />
        <button type="button" onClick={handleUpload} disabled={uploading}>
          {uploading ? 'Uploading…' : resume ? 'Replace Resume' : 'Upload Resume'}
        </button>
      </div>
      {error && (
        <p className="status-error-text" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
