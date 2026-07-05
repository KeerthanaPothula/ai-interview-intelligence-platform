import { useState, type FormEvent } from 'react';
import { Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ApiError, forgotPassword } from '../api/client';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await forgotPassword({ email });
      setSubmitted(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Something went wrong. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="auth-page">
        <div className="auth-form" style={{ textAlign: 'center' }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: 'var(--info-bg)',
              border: '1px solid rgba(59,130,246,0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.25rem',
              fontSize: '1.5rem',
            }}
          >
            ✉
          </div>
          <h1 style={{ marginTop: 0 }}>Check your inbox</h1>
          <p style={{ color: 'var(--muted)', marginBottom: '1.5rem', lineHeight: 1.6 }}>
            If an account exists for <strong style={{ color: 'var(--text)' }}>{email}</strong>,
            we've sent a password reset link. Check your spam folder if it doesn't appear.
          </p>
          <Link to="/login" className="auth-link">
            ← Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-logo">
          <div className="auth-logo-dot" aria-hidden="true" />
          AIIP
        </div>

        <h1>Reset password</h1>
        <p className="auth-subtitle">
          Enter your email and we'll send a reset link if an account exists.
        </p>

        <label htmlFor="fp-email" style={{ marginBottom: '0.3rem' }}>
          Email address
        </label>
        <div className="auth-input-wrap" style={{ marginBottom: '1.25rem' }}>
          <Mail className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="fp-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="you@example.com"
            required
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>

        {error && (
          <p
            role="alert"
            style={{
              color: 'var(--error-text)',
              background: 'var(--error-bg)',
              border: '1px solid rgba(239,68,68,0.2)',
              padding: '0.6rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.84rem',
              margin: '0 0 1rem',
            }}
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          className="btn btn-primary btn-full"
          disabled={submitting}
          aria-busy={submitting}
        >
          {submitting ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Sending link…
            </>
          ) : (
            'Send reset link'
          )}
        </button>

        <p className="auth-footer-text">
          <Link to="/login" className="auth-link">
            ← Back to sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
