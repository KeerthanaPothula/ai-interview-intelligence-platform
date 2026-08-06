import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { RequireRole } from './components/RequireRole';
import { AuthProvider } from './context/AuthContext';
import { FeaturesProvider } from './context/FeaturesContext';
import { RoleProvider } from './context/RoleContext';
import { ThemeProvider } from './context/ThemeContext';
import { ToastProvider } from './context/ToastContext';

// Eagerly load the shell pages (tiny, used on first render)
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { UnauthorizedPage } from './pages/UnauthorizedPage';
import { NotFoundPage } from './pages/NotFoundPage';

// Lazy-load authenticated feature pages (Phase 12 — route-based code splitting)
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const SessionsListPage = lazy(() =>
  import('./pages/SessionsListPage').then((m) => ({ default: m.SessionsListPage })),
);
const SessionDetailPage = lazy(() =>
  import('./pages/SessionDetailPage').then((m) => ({ default: m.SessionDetailPage })),
);
const InterviewReportPage = lazy(() =>
  import('./pages/InterviewReportPage').then((m) => ({ default: m.InterviewReportPage })),
);
const LiveInterviewPage = lazy(() =>
  import('./pages/LiveInterviewPage').then((m) => ({ default: m.LiveInterviewPage })),
);
const AnalyticsPage = lazy(() =>
  import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
);
const ResumePage = lazy(() =>
  import('./pages/ResumePage').then((m) => ({ default: m.ResumePage })),
);
const ProfilePage = lazy(() =>
  import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })),
);
const RecruiterPage = lazy(() =>
  import('./pages/RecruiterPage').then((m) => ({ default: m.RecruiterPage })),
);
const AdminPage = lazy(() =>
  import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })),
);

function PageFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} aria-label="Loading page" />
    </div>
  );
}

// Role gates, matching Phase 4's page-visibility spec exactly: Candidate
// pages are also reachable by Super Admin ("Super Admin: Everything");
// Recruiter's and Admin's own dashboards are not reachable by each other,
// or by Super Admin's peers — only by Super Admin itself. Settings
// (/profile) is common to every role.
const CANDIDATE_ROLES = ['candidate', 'super_admin'] as const;
const RECRUITER_ROLES = ['recruiter', 'super_admin'] as const;
const ADMIN_ROLES = ['admin', 'super_admin'] as const;
const ANY_ROLE = ['candidate', 'recruiter', 'admin', 'super_admin'] as const;

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <RoleProvider>
            <FeaturesProvider>
              <BrowserRouter>
                <Routes>
                  <Route path="/" element={<LandingPage />} />
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                  <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
                  <Route element={<Layout />}>
                    <Route path="/unauthorized" element={<UnauthorizedPage />} />
                    <Route
                      path="/sessions"
                      element={
                        <RequireRole roles={[...CANDIDATE_ROLES]}>
                          <Suspense fallback={<PageFallback />}><SessionsListPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/sessions/:sessionId"
                      element={
                        <RequireRole roles={[...CANDIDATE_ROLES]}>
                          <Suspense fallback={<PageFallback />}><SessionDetailPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/sessions/:sessionId/report"
                      element={
                        // Reachable by Recruiter too — this is the "Open
                        // report" link from the Recruiter dashboard's
                        // candidate detail panel (Phase 8), not just a
                        // candidate reviewing their own report.
                        <RequireRole roles={[...CANDIDATE_ROLES, 'recruiter']}>
                          <Suspense fallback={<PageFallback />}><InterviewReportPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/dashboard"
                      element={
                        <RequireRole roles={[...CANDIDATE_ROLES]}>
                          <Suspense fallback={<PageFallback />}><DashboardPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/live-interview"
                      element={
                        <RequireRole roles={[...CANDIDATE_ROLES]}>
                          <Suspense fallback={<PageFallback />}><LiveInterviewPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/analytics"
                      element={
                        <RequireRole roles={[...CANDIDATE_ROLES]}>
                          <Suspense fallback={<PageFallback />}><AnalyticsPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/resume"
                      element={
                        <RequireRole roles={[...CANDIDATE_ROLES]}>
                          <Suspense fallback={<PageFallback />}><ResumePage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/profile"
                      element={
                        <RequireRole roles={[...ANY_ROLE]}>
                          <Suspense fallback={<PageFallback />}><ProfilePage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/recruiter"
                      element={
                        <RequireRole roles={[...RECRUITER_ROLES]}>
                          <Suspense fallback={<PageFallback />}><RecruiterPage /></Suspense>
                        </RequireRole>
                      }
                    />
                    <Route
                      path="/admin"
                      element={
                        <RequireRole roles={[...ADMIN_ROLES]}>
                          <Suspense fallback={<PageFallback />}><AdminPage /></Suspense>
                        </RequireRole>
                      }
                    />
                  </Route>
                  <Route path="*" element={<NotFoundPage />} />
                </Routes>
              </BrowserRouter>
            </FeaturesProvider>
          </RoleProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
