import { NavLink, useNavigate } from 'react-router-dom';
import {
  BarChart2,
  LayoutDashboard,
  LogOut,
  Mic,
  FileText,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: FileText, label: 'Interviews' },
  { to: '/live-interview', icon: Mic, label: 'Live Interview' },
  { to: '/sessions', icon: BarChart2, label: 'Analytics', end: false },
];

export function Sidebar() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/');
  }

  return (
    <aside className="sb-sidebar" aria-label="Main navigation">
      <div className="sb-sidebar-logo">
        <div className="sb-sidebar-logo-dot" aria-hidden="true" />
        <span className="sb-sidebar-logo-text">AIIP</span>
      </div>

      <nav className="sb-nav" aria-label="Primary">
        <div className="sb-nav-section">
          <div className="sb-nav-label">Platform</div>
          {NAV.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={label}
              to={to}
              end={end ?? true}
              className={({ isActive }) =>
                'sb-nav-item' + (isActive ? ' active' : '')
              }
              aria-label={label}
            >
              <Icon className="sb-nav-icon" aria-hidden="true" size={18} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      <div className="sb-sidebar-footer">
        <button
          className="sb-nav-item"
          onClick={handleLogout}
          aria-label="Log out"
        >
          <LogOut className="sb-nav-icon" aria-hidden="true" size={18} />
          Log out
        </button>
      </div>
    </aside>
  );
}

export function SidebarShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="sb-shell">
      <Sidebar />
      {children}
    </div>
  );
}
