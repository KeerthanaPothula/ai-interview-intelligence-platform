import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RequireRole } from './RequireRole';
import { RoleProvider } from '../context/RoleContext';
import type { UserResponse } from '../api/types';

let mockUser: UserResponse | null = null;
let mockUserLoading = false;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: mockUser ? 'test-token' : null,
      user: mockUser,
      userLoading: mockUserLoading,
      isAuthenticated: mockUser !== null,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })),
  };
});

function makeUser(role: UserResponse['role']): UserResponse {
  return {
    id: 'user-1',
    email: 'jane@example.com',
    full_name: 'Jane Smith',
    role,
    organization: null,
    created_at: '2026-01-01T00:00:00Z',
  };
}

function renderProtected(roles: UserResponse['role'][]) {
  return render(
    <MemoryRouter initialEntries={['/protected']}>
      <RoleProvider>
        <Routes>
          <Route path="/unauthorized" element={<div>403 page</div>} />
          <Route
            path="/protected"
            element={
              <RequireRole roles={roles}>
                <div>Protected content</div>
              </RequireRole>
            }
          />
        </Routes>
      </RoleProvider>
    </MemoryRouter>,
  );
}

describe('RequireRole', () => {
  it('renders children when the role is allowed', () => {
    mockUser = makeUser('recruiter');
    mockUserLoading = false;
    renderProtected(['recruiter', 'super_admin']);
    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });

  it('redirects to /unauthorized when the role is not allowed', () => {
    mockUser = makeUser('candidate');
    mockUserLoading = false;
    renderProtected(['recruiter', 'super_admin']);
    expect(screen.getByText('403 page')).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('redirects to /unauthorized when there is no user at all', () => {
    mockUser = null;
    mockUserLoading = false;
    renderProtected(['candidate']);
    expect(screen.getByText('403 page')).toBeInTheDocument();
  });

  it('shows a loading state instead of redirecting while the role is still loading', () => {
    mockUser = null;
    mockUserLoading = true;
    renderProtected(['candidate']);
    expect(screen.queryByText('403 page')).not.toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Loading')).toBeInTheDocument();
  });

  it('allows Super Admin into a Candidate-only route when explicitly included', () => {
    mockUser = makeUser('super_admin');
    mockUserLoading = false;
    renderProtected(['candidate', 'super_admin']);
    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });
});
