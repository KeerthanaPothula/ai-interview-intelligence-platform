import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { OfflineBanner } from './OfflineBanner';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/sessions': 'Interviews',
  '/live-interview': 'Live Interview',
  '/analytics': 'Analytics',
  '/resume': 'Resume Analyzer',
  '/profile': 'Profile & Settings',
};

export function Layout() {
  const { isAuthenticated } = useAuth();
  const { pathname } = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const title =
    PAGE_TITLES[pathname] ??
    (pathname.endsWith('/report') ? 'Interview Report' :
     pathname.startsWith('/sessions/') ? 'Session Detail' :
     'AI Interview Platform');

  return (
    <>
      <OfflineBanner />
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
    </>
  );
}
