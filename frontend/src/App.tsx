import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AuthProvider } from './context/AuthContext';
import { FeaturesProvider } from './context/FeaturesContext';
import { ToastProvider } from './context/ToastContext';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { DashboardPage } from './pages/DashboardPage';
import { ForgotPasswordPage } from './pages/ForgotPasswordPage';
import { LandingPage } from './pages/LandingPage';
import { LiveInterviewPage } from './pages/LiveInterviewPage';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ProfilePage } from './pages/ProfilePage';
import { RegisterPage } from './pages/RegisterPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { ResumePage } from './pages/ResumePage';
import { SessionDetailPage } from './pages/SessionDetailPage';
import { SessionsListPage } from './pages/SessionsListPage';

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
                <Route path="/sessions" element={<SessionsListPage />} />
                <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/live-interview" element={<LiveInterviewPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/resume" element={<ResumePage />} />
                <Route path="/profile" element={<ProfilePage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </BrowserRouter>
        </FeaturesProvider>
      </AuthProvider>
    </ToastProvider>
  );
}
