import { Link, Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function Layout() {
  const { isAuthenticated, logout } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="app-title">
          AI Interview Intelligence Platform
        </Link>
        <nav className="app-nav">
          <Link to="/" className="nav-link">Sessions</Link>
          <Link to="/dashboard" className="nav-link">Dashboard</Link>
          <Link to="/live-interview" className="nav-link">Live Interview</Link>
        </nav>
        <button type="button" onClick={logout}>
          Log out
        </button>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
