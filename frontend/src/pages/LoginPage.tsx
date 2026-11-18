import { useState, type FormEvent } from 'react';
import { Eye, EyeOff, Lock, Mail } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { homeRouteForRole } from '../utils/roleRoutes';
import { useSlowFlag } from '../hooks/useSlowFlag';

export function LoginPage() {
  const { login, isAuthenticated, user, userLoading } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  // After a successful login the role is still loading (/auth/me in flight):
  // keep the button busy until the redirect below fires. A token restored
  // from storage neither blocks the form (on a cold backend that check can
  // take ~30 s) nor redirects: /login always shows the login form.
  const busy = submitting || (loggedIn && userLoading);
  const slow = useSlowFlag(busy);

  // Redirect only after THIS form's login, once the backend has verified the
  // new token (login() clears the previous user, so isAuthenticated here
  // means /auth/me answered for the new session and `user` is its user).
  if (loggedIn && isAuthenticated) {
    return <Navigate to={homeRouteForRole(user?.role ?? null)} replace />;
  }
  // Login succeeded but /auth/me failed (network error): say so instead of
  // silently re-enabling the form.
  const profileError =
    loggedIn && !busy ? 'Signed in, but your profile could not be loaded. Please try again.' : null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoggedIn(false);
    setSubmitting(true);
    try {
      await login(email, password, rememberMe);
      setLoggedIn(true);
    } catch (err) {
      // ApiError's message is the backend's own detail text for 4xx errors
      // (see client.ts's extractErrorMessage) — e.g. "Incorrect email or
      // password." for a bad login, "Account temporarily locked..." for a
      // 423 — already specific and safe to show verbatim, no per-status
      // special-casing needed here.
      setError(err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.');
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
          <label className="auth-checkbox-label">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            Remember me
          </label>
          <Link to="/forgot-password" className="auth-link">
            Forgot password?
          </Link>
        </div>

        {(error ?? profileError) && (
          <p
            role="alert"
            style={{
              color: 'var(--error-text)',
              background: 'var(--error-bg)',
              border: '1px solid var(--error-border)',
              padding: '0.6rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.84rem',
              margin: '0 0 1rem',
            }}
          >
            {error ?? profileError}
          </p>
        )}

        <button
          type="submit"
          className="btn btn-primary btn-full"
          disabled={busy}
          aria-busy={busy}
        >
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Signing in…
            </>
          ) : (
            'Sign in'
          )}
        </button>

        {slow && (
          <p role="status" className="auth-footer-text">
            The server is waking up after being idle. This can take up to a minute.
          </p>
        )}

        <p className="auth-footer-text">
          Don&apos;t have an account?{' '}
          <Link to="/register">Create one free</Link>
        </p>
      </form>
    </div>
  );
}
