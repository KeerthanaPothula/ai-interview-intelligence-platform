import { useState, type FormEvent } from 'react';
import { Eye, EyeOff, Lock, Mail } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/sessions" replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 423) {
        setError('Account temporarily locked due to multiple failed attempts. Try again later.');
      } else {
        setError(err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-logo">
          <div className="auth-logo-dot" aria-hidden="true" />
          AIIP
        </div>

        <h1>Welcome back</h1>
        <p className="auth-subtitle">Sign in to your account to continue</p>

        <label htmlFor="login-email" style={{ marginBottom: '0.3rem' }}>
          Email
        </label>
        <div className="auth-input-wrap" style={{ marginBottom: '1rem' }}>
          <Mail className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="login-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="you@example.com"
            required
            style={{ paddingLeft: '2.25rem' }}
          />
        </div>

        <label htmlFor="login-password" style={{ marginBottom: '0.3rem' }}>
          Password
        </label>
        <div className="auth-input-wrap has-toggle" style={{ marginBottom: '0.5rem' }}>
          <Lock className="auth-input-icon" size={16} aria-hidden="true" />
          <input
            id="login-password"
            type={showPw ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            placeholder="••••••••"
            required
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

        <div className="auth-options" style={{ marginBottom: '1.25rem' }}>
          <span />
          <Link to="/forgot-password" className="auth-link">
            Forgot password?
          </Link>
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
              Signing in…
            </>
          ) : (
            'Sign in'
          )}
        </button>

        <p className="auth-footer-text">
          Don&apos;t have an account?{' '}
          <Link to="/register">Create one free</Link>
        </p>
      </form>
    </div>
  );
}
