import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './Layout';

let mockIsAuthenticated = false;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: mockIsAuthenticated ? 'test-token' : null,
      user: null,
      isAuthenticated: mockIsAuthenticated,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })),
  };
});

// Sidebar/TopBar pull in a lot (NotificationBell, UserMenu, ThemeToggle,
// framer-motion) that isn't relevant to route-guard behavior — stub them so
// this test is only exercising Layout's own auth check.
vi.mock('./Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
vi.mock('./TopBar', () => ({ TopBar: () => <header data-testid="topbar" /> }));
vi.mock('./OfflineBanner', () => ({ OfflineBanner: () => null }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<div>Dashboard content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockIsAuthenticated = false;
});

describe('Layout (protected route guard)', () => {
  it('redirects unauthenticated users to /login instead of rendering protected content', () => {
    renderAt('/dashboard');
    expect(screen.getByText('Login page')).toBeInTheDocument();
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument();
  });

  it('renders the protected content and app shell for authenticated users', () => {
    mockIsAuthenticated = true;
    renderAt('/dashboard');
    expect(screen.getByText('Dashboard content')).toBeInTheDocument();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('topbar')).toBeInTheDocument();
  });
});
