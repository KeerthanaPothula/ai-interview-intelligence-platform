import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/sessions': 'Interviews',
  '/live-interview': 'Live Interview',
};

export function Layout() {
  const { isAuthenticated } = useAuth();
  const { pathname } = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const title = PAGE_TITLES[pathname] ?? 'AI Interview Platform';

  return (
    <div className="sb-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <Sidebar />
      <TopBar title={title} />
      <main className="sb-content" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
