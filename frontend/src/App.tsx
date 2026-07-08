import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AuthProvider } from './context/AuthContext';
import { FeaturesProvider } from './context/FeaturesContext';
import { ToastProvider } from './context/ToastContext';

// Eagerly load the shell pages (tiny, used on first render)
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
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

function PageFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} aria-label="Loading page" />
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <FeaturesProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
              <Route element={<Layout />}>
                <Route
                  path="/sessions"
                  element={<Suspense fallback={<PageFallback />}><SessionsListPage /></Suspense>}
                />
                <Route
                  path="/sessions/:sessionId"
                  element={<Suspense fallback={<PageFallback />}><SessionDetailPage /></Suspense>}
                />
                <Route
                  path="/sessions/:sessionId/report"
                  element={<Suspense fallback={<PageFallback />}><InterviewReportPage /></Suspense>}
                />
                <Route
                  path="/dashboard"
                  element={<Suspense fallback={<PageFallback />}><DashboardPage /></Suspense>}
                />
                <Route
                  path="/live-interview"
                  element={<Suspense fallback={<PageFallback />}><LiveInterviewPage /></Suspense>}
                />
                <Route
                  path="/analytics"
                  element={<Suspense fallback={<PageFallback />}><AnalyticsPage /></Suspense>}
                />
                <Route
                  path="/resume"
                  element={<Suspense fallback={<PageFallback />}><ResumePage /></Suspense>}
                />
                <Route
                  path="/profile"
                  element={<Suspense fallback={<PageFallback />}><ProfilePage /></Suspense>}
                />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </BrowserRouter>
        </FeaturesProvider>
      </AuthProvider>
    </ToastProvider>
  );
}
