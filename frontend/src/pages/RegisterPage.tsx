import { useState, type FormEvent } from 'react';
import { Eye, EyeOff, Lock, Mail, User } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';

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

export function RegisterPage() {
  const { register, isAuthenticated } = useAuth();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const strength = passwordStrength(password);

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (password !== confirmPw) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (!acceptTerms) {
      setError('You must accept the Terms of Service to create an account.');
      return;
    }

    setSubmitting(true);
    try {
      const fullName = `${firstName.trim()} ${lastName.trim()}`.trim();
      await register({ email, password, full_name: fullName });
      // register() auto-logs-in on success — if that worked, isAuthenticated
      // is now true and the guard above redirects to /dashboard on the next
      // render. Reaching this line without isAuthenticated flipping means
      // auto-login didn't happen (rare — see AuthContext.register), so fall
      // back to the manual "sign in" success screen below.
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to register. Please try again.');
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
          <h1 style={{ marginTop: 0 }}>Account created!</h1>
          <p style={{ color: 'var(--muted)', marginBottom: '1.5rem' }}>
            Your account is ready. Sign in to start your first interview.
          </p>
          <Link
            to="/login"
            className="btn btn-primary"
            style={{ display: 'inline-flex' }}
          >
            Sign in now
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

        <h1>Create an account</h1>
        <p className="auth-subtitle">Start your interview preparation journey</p>

        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
          <div style={{ flex: 1 }}>
            <label htmlFor="reg-first-name" style={{ marginBottom: '0.3rem' }}>
              First name
            </label>
            <div className="auth-input-wrap">
              <User className="auth-input-icon" size={16} aria-hidden="true" />
              <input
                id="reg-first-name"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                autoComplete="given-name"
                placeholder="Jane"
                required
                style={{ paddingLeft: '2.25rem' }}
              />
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <label htmlFor="reg-last-name" style={{ marginBottom: '0.3rem' }}>
              Last name
            </label>
            <div className="auth-input-wrap">
              <input
                id="reg-last-name"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name"
                placeholder="Smith"
                required
                style={{ paddingLeft: '0.75rem' }}
              />
            </div>
          </div>
        </div>

        <label htmlFor="reg-email" style={{ marginBottom: '0.3rem' }}>
          Email
        </label>
        <div className="auth-input-wrap" style={{ marginBottom: '1rem' }}>
          <Mail className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="reg-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="you@example.com"
            required
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>

        <label htmlFor="reg-password" style={{ marginBottom: '0.3rem' }}>
          Password
        </label>
        <div className="auth-input-wrap has-toggle" style={{ marginBottom: '0.35rem' }}>
          <Lock className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="reg-password"
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
          htmlFor="reg-confirm"
          style={{ marginBottom: '0.3rem', marginTop: '1rem' }}
        >
          Confirm password
        </label>
        <div className="auth-input-wrap" style={{ marginBottom: '1.25rem' }}>
          <Lock className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="reg-confirm"
            type={showPw ? 'text' : 'password'}
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            autoComplete="new-password"
            placeholder="Repeat password"
            required
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>

        <div className="auth-options" style={{ justifyContent: 'flex-start' }}>
          <label className="auth-checkbox-label" htmlFor="reg-accept-terms">
            <input
              id="reg-accept-terms"
              type="checkbox"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
              required
            />
            I agree to the Terms of Service and Privacy Policy
          </label>
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
              Creating account…
            </>
          ) : (
            'Create account'
          )}
        </button>

        <p className="auth-footer-text">
          Already have an account?{' '}
          <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
