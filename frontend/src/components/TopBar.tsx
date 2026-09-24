import { NotificationBell } from './NotificationBell';
import { ThemeToggle } from './ThemeToggle';
import { UserMenu } from './UserMenu';

interface TopBarProps {
  title?: string;
}

export function TopBar({ title }: TopBarProps) {
  return (
    <header className="sb-topbar" role="banner">
      {title && (
        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text)' }}>
          {title}
        </span>
      )}

      <div className="sb-topbar-spacer" />

      <div className="sb-topbar-actions">
        <ThemeToggle />
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  );
}
