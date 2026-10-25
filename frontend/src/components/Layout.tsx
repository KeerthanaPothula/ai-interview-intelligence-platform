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
  '/recruiter': 'Recruiter Dashboard',
  '/admin': 'Admin Dashboard',
};

export function Layout() {
  const { isAuthenticated, userLoading } = useAuth();
  const { pathname } = useLocation();

  // A stored token is still being verified against /auth/me — show nothing
  // protected until the backend answers. Skipped when a verified user is
  // already present (silent token refresh), so pages aren't unmounted.
  if (userLoading && !isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} aria-label="Checking your session" />
      </div>
    );
  }

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

