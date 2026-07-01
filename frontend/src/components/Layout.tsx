import { Link, NavLink, Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function navLinkClassName({ isActive }: { isActive: boolean }) {
  return isActive ? 'nav-link nav-link-active' : 'nav-link';
}

export function Layout() {
  const { isAuthenticated, logout } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <header className="app-header">
        <Link to="/sessions" className="app-title">
          AI Interview Intelligence Platform
        </Link>
        <nav className="app-nav" aria-label="Primary">
          <NavLink to="/sessions" end className={navLinkClassName}>
            Sessions
          </NavLink>
          <NavLink to="/dashboard" className={navLinkClassName}>
            Dashboard
          </NavLink>
          <NavLink to="/live-interview" className={navLinkClassName}>
            Live Interview
          </NavLink>
        </nav>
        <button type="button" onClick={logout}>
          Log out
        </button>
      </header>
      <main className="app-main" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
