import { type FormEvent, useEffect, useState } from 'react';
import { Bell, Globe, KeyRound, Shield, Sun, Trash2, User } from 'lucide-react';
import { ApiError, changePassword, logoutAllSessions, updateProfile } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useTheme, type Theme } from '../context/ThemeContext';
import { useToast } from '../context/ToastContext';

const THEME_OPTIONS: { value: Theme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

type Tab = 'account' | 'security' | 'danger';

const TABS: { key: Tab; label: string; icon: typeof User }[] = [
  { key: 'account', label: 'Account', icon: User },
  { key: 'security', label: 'Security', icon: Shield },
  { key: 'danger', label: 'Danger Zone', icon: Trash2 },
];

function initials(name: string | undefined): string {
  if (!name) return '?';
  return name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

export function ProfilePage() {
  const { token, logout, user, userLoading, refreshUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const { showToast } = useToast();
  const [tab, setTab] = useState<Tab>('account');

  function handleThemeChange(next: Theme) {
    if (next === theme) return;
    setTheme(next);
    showToast(`Theme set to ${next === 'light' ? 'Light' : 'Dark'}.`, 'success');
  }

  // Profile form state — seeded from the AuthContext user once it loads,
  // then edited locally. `user` only ever changes on mount and right after
  // our own save (via refreshUser), so this never clobbers an in-progress
  // edit with a background refetch.
  const [fullName, setFullName] = useState('');
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);

  useEffect(() => {
    if (user) setFullName(user.full_name);
  }, [user]);

  async function handleSaveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileError(null);
    const trimmed = fullName.trim();
    if (!trimmed) {
      setProfileError('Name cannot be empty.');
      return;
    }
    if (!token) return;
    setProfileSaving(true);
    try {
      await updateProfile({ full_name: trimmed }, token);
      await refreshUser();
      showToast('Profile updated.', 'success');
    } catch (err) {
      setProfileError(
        err instanceof ApiError ? err.message : 'Unable to update profile. Please try again.',
      );
    } finally {
      setProfileSaving(false);
    }
  }

  // Change password form state
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSaving, setPwSaving] = useState(false);

  // Sign out of all sessions
  const [loggingOutAll, setLoggingOutAll] = useState(false);

  async function handleLogoutAll() {
    if (!token) return;
    if (
      !window.confirm(
        'This will sign you out on every device, including this one. Continue?',
      )
    ) {
      return;
    }
    setLoggingOutAll(true);
    try {
      await logoutAllSessions(token);
      showToast('Signed out of all sessions.', 'success');
      logout();
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.message : 'Unable to sign out of all sessions.',
        'error',
      );
    } finally {
      setLoggingOutAll(false);
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    setPwError(null);
    if (newPw !== confirmPw) {
      setPwError('New passwords do not match.');
      return;
    }
    if (newPw.length < 8) {
      setPwError('New password must be at least 8 characters.');
      return;
    }
    if (!token) return;
    setPwSaving(true);
    try {
      await changePassword({ current_password: currentPw, new_password: newPw }, token);
      showToast('Password changed successfully. Please log in again.', 'success');
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
      setTimeout(() => logout(), 1500);
    } catch (err) {
      setPwError(
        err instanceof ApiError ? err.message : 'Unable to change password. Please try again.',
      );
    } finally {
      setPwSaving(false);
    }
  }

  return (
    <div className="page-container">
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.35rem' }}>Profile & Settings</h1>
        <p style={{ margin: '0.2rem 0 0', color: 'var(--muted)', fontSize: '0.875rem' }}>
          Manage your account, security, and preferences
        </p>
      </div>

      <div className="profile-layout">
        {/* Sidebar nav */}
        <nav className="profile-sidebar-nav" aria-label="Settings sections">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              className={`profile-nav-item${tab === key ? ' active' : ''}`}
              onClick={() => setTab(key)}
              aria-current={tab === key ? 'page' : undefined}
            >
              <Icon size={16} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div>
          {/* Account tab */}
          {tab === 'account' && (
            <>
              <div className="profile-section">
                <h2 className="profile-section-title">Profile</h2>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', marginBottom: '1.5rem' }}
                >
                  <div className="profile-avatar" aria-hidden="true">
                    {initials(user?.full_name)}
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '0.2rem' }}>
                      Your Account
                    </div>
                    <div style={{ fontSize: '0.84rem', color: 'var(--muted)' }}>
                      Manage your profile information
                    </div>
                  </div>
                </div>

                <form onSubmit={handleSaveProfile} style={{ maxWidth: 420 }}>
                  <label>
                    Full name
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      required
                      maxLength={255}
                      disabled={userLoading}
                      autoComplete="name"
                    />
                  </label>
                  <label>
                    Email
                    <input type="email" value={user?.email ?? ''} disabled readOnly />
                    <span className="field-hint">Email cannot be changed here.</span>
                  </label>

                  {profileError && (
                    <p
                      role="alert"
                      style={{
                        color: 'var(--error-text)',
                        background: 'var(--error-bg)',
                        border: '1px solid var(--error-border)',
                        padding: '0.55rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.84rem',
                        margin: '0.5rem 0',
                      }}
                    >
                      {profileError}
                    </p>
                  )}

                  <button
                    type="submit"
                    className="btn btn-primary btn-sm"
                    disabled={profileSaving || userLoading}
                    aria-busy={profileSaving}
                    style={{ marginTop: '0.5rem' }}
                  >
                    {profileSaving ? (
                      <>
                        <span className="spinner" aria-hidden="true" />
                        Saving…
                      </>
                    ) : (
                      'Save Changes'
                    )}
                  </button>
                </form>
              </div>

              <div className="profile-section">
                <h2 className="profile-section-title">
                  <Sun size={16} style={{ display: 'inline', marginRight: 6 }} aria-hidden="true" />
                  Appearance
                </h2>
                <div style={{ maxWidth: 420 }}>
                  {/* A plain caption, not a <label>: it describes the whole
                      radiogroup below (which already carries its own
                      aria-label="Theme"), not one specific control — a
                      htmlFor/id pairing here would override that option
                      button's own accessible name instead of naming the
                      group. */}
                  <div style={{ marginBottom: '0.4rem' }}>Theme</div>
                  <div className="li-turn-options" role="radiogroup" aria-label="Theme">
                    {THEME_OPTIONS.map(({ value, label }) => (
                      <button
                        key={value}
                        type="button"
                        role="radio"
                        aria-checked={theme === value}
                        className={`li-turn-opt${theme === value ? ' selected' : ''}`}
                        onClick={() => handleThemeChange(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <span className="field-hint">
                    Applies immediately and is remembered on this device.
                  </span>
                </div>
              </div>

              <div className="profile-section">
                <h2 className="profile-section-title">
                  <Bell size={16} style={{ display: 'inline', marginRight: 6 }} aria-hidden="true" />
                  Notifications
                </h2>
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    background: 'var(--surface-2)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.85rem',
                    color: 'var(--muted)',
                  }}
                >
                  Notification preferences aren't available yet — there is no notification
                  system in the app to configure. This will be added once real notifications
                  (e.g. email or in-app alerts) exist to control.
                </div>
              </div>

              <div className="profile-section">
                <h2 className="profile-section-title">
                  <Globe size={16} style={{ display: 'inline', marginRight: 6 }} aria-hidden="true" />
                  Regional
                </h2>
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    background: 'var(--surface-2)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.85rem',
                    color: 'var(--muted)',
                  }}
                >
                  Timezone preferences aren't available yet — every date and time shown in the
                  app already uses your browser's local timezone automatically, so there is
                  nothing to configure yet.
                </div>
              </div>
            </>
          )}

          {/* Security tab */}
          {tab === 'security' && (
            <div className="profile-section">
              <h2 className="profile-section-title">
                <KeyRound size={16} style={{ display: 'inline', marginRight: 6 }} aria-hidden="true" />
                Change Password
              </h2>
              <form onSubmit={handleChangePassword} style={{ maxWidth: 420 }}>
                <label>
                  Current password
                  <input
                    type="password"
                    value={currentPw}
                    onChange={(e) => setCurrentPw(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                </label>
                <label>
                  New password
                  <input
                    type="password"
                    value={newPw}
                    onChange={(e) => setNewPw(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                  />
                  <span className="field-hint">Minimum 8 characters.</span>
                </label>
                <label>
                  Confirm new password
                  <input
                    type="password"
                    value={confirmPw}
                    onChange={(e) => setConfirmPw(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </label>

                {pwError && (
                  <p
                    role="alert"
                    style={{
                      color: 'var(--error-text)',
                      background: 'var(--error-bg)',
                      border: '1px solid var(--error-border)',
                      padding: '0.55rem 0.75rem',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.84rem',
                      margin: '0.5rem 0',
                    }}
                  >
                    {pwError}
                  </p>
                )}

                <button
                  type="submit"
                  className="btn btn-primary btn-sm"
                  disabled={pwSaving}
                  aria-busy={pwSaving}
                  style={{ marginTop: '0.5rem' }}
                >
                  {pwSaving ? (
                    <>
                      <span className="spinner" aria-hidden="true" />
                      Saving…
                    </>
                  ) : (
                    'Change Password'
                  )}
                </button>
              </form>
            </div>
          )}

          {tab === 'security' && (
            <div className="profile-section">
              <h2 className="profile-section-title">
                <Shield size={16} style={{ display: 'inline', marginRight: 6 }} aria-hidden="true" />
                Sessions
              </h2>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '1rem',
                  flexWrap: 'wrap',
                  padding: '1rem',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text)', marginBottom: '0.2rem' }}>
                    Sign out of all sessions
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
                    Ends every active session on every device, including this one.
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={handleLogoutAll}
                  disabled={loggingOutAll}
                  aria-busy={loggingOutAll}
                  style={{ flexShrink: 0 }}
                >
                  {loggingOutAll ? (
                    <>
                      <span className="spinner" aria-hidden="true" />
                      Signing out…
                    </>
                  ) : (
                    'Sign out everywhere'
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Danger zone tab */}
          {tab === 'danger' && (
            <div className="profile-section danger-zone">
              <h2 className="profile-section-title">Danger Zone</h2>
              <div
                style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                    flexWrap: 'wrap',
                    padding: '1rem',
                    background: 'rgba(239,68,68,0.04)',
                    border: '1px solid rgba(239,68,68,0.15)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text)', marginBottom: '0.2rem' }}>
                      Delete Account
                    </div>
                    <div style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
                      Permanently delete your account and all interview data.
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm"
                    style={{
                      background: 'var(--danger-solid)',
                      color: '#fff',
                      border: 'none',
                      flexShrink: 0,
                    }}
                    onClick={() =>
                      showToast('Account deletion is not available in this demo.', 'info')
                    }
                  >
                    Delete Account
                  </button>
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                    flexWrap: 'wrap',
                    padding: '1rem',
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text)', marginBottom: '0.2rem' }}>
                      Export Data
                    </div>
                    <div style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
                      Download all your interview sessions, reports, and analytics.
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => showToast('Data export is coming soon.', 'info')}
                  >
                    Export Data
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
