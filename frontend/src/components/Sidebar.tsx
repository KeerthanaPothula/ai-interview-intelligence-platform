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
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useRole } from '../context/RoleContext';

interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
}

// One list per role — Phase 5: "Sidebar should automatically change based
// on role. No hidden links. No dead routes." Every entry here has a
// matching <RequireRole roles={...}> gate on the same path in App.tsx, so
// a link is never shown for a page the current role can't actually open.
const CANDIDATE_NAV: NavItem[] = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sessions', icon: FileText, label: 'Interviews' },
  { to: '/live-interview', icon: Mic, label: 'Live Interview' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics' },
  { to: '/resume', icon: Upload, label: 'Resume' },
];

const RECRUITER_NAV: NavItem[] = [
  { to: '/recruiter', icon: Users, label: 'Recruiter Dashboard' },
];

const ADMIN_NAV: NavItem[] = [
  { to: '/admin', icon: ShieldCheck, label: 'Admin Dashboard' },
];

// Super Admin: "Everything" (Phase 4) — the union of every other role's nav.
const SUPER_ADMIN_NAV: NavItem[] = [...CANDIDATE_NAV, ...RECRUITER_NAV, ...ADMIN_NAV];

function navForRole(role: ReturnType<typeof useRole>['role']): NavItem[] {
  switch (role) {
    case 'recruiter':
      return RECRUITER_NAV;
    case 'admin':
      return ADMIN_NAV;
    case 'super_admin':
      return SUPER_ADMIN_NAV;
    case 'candidate':
    default:
      return CANDIDATE_NAV;
  }
}

export function Sidebar() {
  const { logout } = useAuth();
  const { role } = useRole();
  const navigate = useNavigate();
  const nav = navForRole(role);

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
          {nav.map(({ to, icon: Icon, label }) => (
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
