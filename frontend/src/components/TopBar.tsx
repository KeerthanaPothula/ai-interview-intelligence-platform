import { Search } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { NotificationBell } from './NotificationBell';
import { ThemeToggle } from './ThemeToggle';

interface TopBarProps {
  title?: string;
}

export function TopBar({ title }: TopBarProps) {
  const { token } = useAuth();
  const initials = token ? 'U' : '?';

  return (
    <header className="sb-topbar" role="banner">
      {title && (
        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text)' }}>
          {title}
        </span>
      )}

      <div className="sb-topbar-spacer" />

      <div className="sb-topbar-search" role="search" aria-label="Search">
        <Search size={14} aria-hidden="true" />
        <span style={{ fontSize: '0.82rem' }}>Search…</span>
        <span
          style={{
            marginLeft: 'auto',
            fontSize: '0.7rem',
            background: 'var(--surface-3)',
            padding: '0.1rem 0.35rem',
            borderRadius: '4px',
            color: 'var(--muted)',
          }}
        >
          ⌘K
        </span>
      </div>

      <div className="sb-topbar-actions">
        <ThemeToggle />
        <NotificationBell />

        <div className="sb-avatar" role="button" aria-label="Profile menu" tabIndex={0}>
          {initials}
        </div>
      </div>
    </header>
  );
}
