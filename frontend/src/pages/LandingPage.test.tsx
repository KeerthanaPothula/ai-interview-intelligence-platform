import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LandingPage } from './LandingPage';
import { RoleProvider } from '../context/RoleContext';

let mockIsAuthenticated = false;
let mockUser: { role: string } | null = null;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: mockIsAuthenticated ? 'saved' : null,
      user: mockUser,
      userLoading: false,
      isAuthenticated: mockIsAuthenticated,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })),
  };
});

beforeAll(() => {
  // jsdom lacks these browser APIs the landing page's animations use.
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
});

beforeEach(() => {
  mockIsAuthenticated = false;
  mockUser = null;
});

function renderLanding() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <RoleProvider>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<p>login form</p>} />
          <Route path="/register" element={<p>register form</p>} />
        </Routes>
      </RoleProvider>
    </MemoryRouter>,
  );
}

const nav = () => within(screen.getByRole('banner'));

describe('LandingPage auth buttons', () => {
  it.each([
    ['signed out', false],
    ['with a valid saved session', true],
  ])('shows both Log in and Get Started (%s)', (_label, authed) => {
    mockIsAuthenticated = authed;
    mockUser = authed ? { role: 'recruiter' } : null;
    renderLanding();
    expect(nav().getByRole('link', { name: /^log in$/i })).toHaveAttribute('href', '/login');
    expect(nav().getByRole('link', { name: /^get started$/i })).toHaveAttribute('href', '/register');
  });

  it('a signed-in user also gets a Dashboard link to their role home', () => {
    mockIsAuthenticated = true;
    mockUser = { role: 'recruiter' };
    renderLanding();
    expect(nav().getByRole('link', { name: /^dashboard$/i })).toHaveAttribute('href', '/recruiter');
  });

  it('Log in opens /login', async () => {
    renderLanding();
    await userEvent.click(nav().getByRole('link', { name: /^log in$/i }));
    expect(screen.getByText('login form')).toBeInTheDocument();
  });

  it('Get Started opens /register', async () => {
    renderLanding();
    await userEvent.click(nav().getByRole('link', { name: /^get started$/i }));
    expect(screen.getByText('register form')).toBeInTheDocument();
  });
});
