import { type FormEvent, useState } from 'react';
import { KeyRound, Shield, Trash2, User } from 'lucide-react';
import { ApiError, changePassword } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

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
  const { token, logout } = useAuth();
  const { showToast } = useToast();
  const [tab, setTab] = useState<Tab>('account');

  // Change password form state
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSaving, setPwSaving] = useState(false);

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
                    {initials('User')}
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
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    background: 'var(--surface-2)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.85rem',
                    color: 'var(--muted)',
                  }}
                >
                  Profile editing is coming soon. Your account is active and secure.
                </div>
              </div>

              <div className="profile-section">
                <h2 className="profile-section-title">Preferences</h2>
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    background: 'var(--surface-2)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.85rem',
                    color: 'var(--muted)',
                  }}
                >
                  Theme, notification, and timezone preferences are coming soon.
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
                      border: '1px solid rgba(239,68,68,0.2)',
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
                      background: 'var(--error)',
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
