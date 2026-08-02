import { NavLink, useNavigate } from 'react-router-dom';
import {
  BarChart2,
  FileText,
  LayoutDashboard,
  LogOut,
  Mic,
  Settings,
  ShieldCheck,
  Upload,
  Users,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: FileText, label: 'Interviews' },
  { to: '/live-interview', icon: Mic, label: 'Live Interview' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics' },
  { to: '/resume', icon: Upload, label: 'Resume' },
  { to: '/recruiter', icon: Users, label: 'Recruiter' },
  { to: '/admin', icon: ShieldCheck, label: 'Admin' },
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
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={label}
              to={to}
              end
              className={({ isActive }) => 'sb-nav-item' + (isActive ? ' active' : '')}
              aria-label={label}
            >
              <Icon className="sb-nav-icon" aria-hidden="true" size={18} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      <div className="sb-sidebar-footer">
        <NavLink
          to="/profile"
          end
          className={({ isActive }) => 'sb-nav-item' + (isActive ? ' active' : '')}
          aria-label="Profile & Settings"
        >
          <Settings className="sb-nav-icon" aria-hidden="true" size={18} />
          Settings
        </NavLink>
        <button
          type="button"
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
