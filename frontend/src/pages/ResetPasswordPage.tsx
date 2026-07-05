import { useState, type FormEvent } from 'react';
import { Eye, EyeOff, Lock } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, resetPassword } from '../api/client';

function passwordStrength(pw: string): 0 | 1 | 2 | 3 | 4 {
  if (pw.length === 0) return 0;
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score as 0 | 1 | 2 | 3 | 4;
}

const STRENGTH_LABEL = ['', 'Weak', 'Fair', 'Good', 'Strong'];

export function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>();
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const strength = passwordStrength(password);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError('Invalid reset link. Please request a new one.');
      return;
    }
    if (password !== confirmPw) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setSubmitting(true);
    try {
      await resetPassword({ token, new_password: password });
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'This reset link is invalid or has expired. Please request a new one.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className="auth-page">
        <div className="auth-form" style={{ textAlign: 'center' }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: 'var(--success-bg)',
              border: '1px solid rgba(34,197,94,0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.25rem',
              fontSize: '1.5rem',
              color: 'var(--success-text)',
            }}
          >
            ✓
          </div>
          <h1 style={{ marginTop: 0 }}>Password updated!</h1>
          <p style={{ color: 'var(--muted)', marginBottom: '1.5rem' }}>
            Your password has been changed. You can now sign in with your new password.
          </p>
          <Link to="/login" className="btn btn-primary" style={{ display: 'inline-flex' }}>
            Sign in
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

        <h1>Set new password</h1>
        <p className="auth-subtitle">Choose a strong password for your account.</p>

        <label htmlFor="rp-password" style={{ marginBottom: '0.3rem' }}>
          New password
        </label>
        <div className="auth-input-wrap has-toggle" style={{ marginBottom: '0.35rem' }}>
          <Lock className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="rp-password"
            type={showPw ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder="At least 8 characters"
            required
            minLength={8}
            style={{ paddingLeft: '2.25rem', paddingRight: '2.5rem' }}
          />
          <button
            type="button"
            className="auth-pw-toggle"
            aria-label={showPw ? 'Hide password' : 'Show password'}
            onClick={() => setShowPw((v) => !v)}
          >
            {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>

        {password.length > 0 && (
          <div className="pw-strength" aria-live="polite">
            <div
              className="pw-strength-bar"
              role="meter"
              aria-valuenow={strength}
              aria-valuemin={0}
              aria-valuemax={4}
              aria-label="Password strength"
            >
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className={`pw-strength-seg${strength >= n ? ` filled-${strength}` : ''}`}
                />
              ))}
            </div>
            <span className="pw-strength-label">{STRENGTH_LABEL[strength]}</span>
          </div>
        )}

        <label
          htmlFor="rp-confirm"
          style={{ marginBottom: '0.3rem', marginTop: '1rem' }}
        >
          Confirm new password
        </label>
        <div className="auth-input-wrap" style={{ marginBottom: '1.25rem' }}>
          <Lock className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="rp-confirm"
            type={showPw ? 'text' : 'password'}
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            autoComplete="new-password"
            placeholder="Repeat new password"
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
              Updating password…
            </>
          ) : (
            'Update password'
          )}
        </button>

        <p className="auth-footer-text">
          <Link to="/forgot-password" className="auth-link">
            Request a new link
          </Link>
        </p>
      </form>
    </div>
  );
}
