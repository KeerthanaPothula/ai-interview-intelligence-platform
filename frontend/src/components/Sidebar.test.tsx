import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import type { UserResponse } from '../api/types';

let mockUser: UserResponse | null = null;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: 'test-token',
      user: mockUser,
      userLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    })),
  };
});

vi.mock('../context/RoleContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/RoleContext')>();
  return {
    ...actual,
    useRole: vi.fn(() => ({
      role: mockUser?.role ?? null,
      roleLoading: false,
      isCandidate: mockUser?.role === 'candidate',
      isRecruiter: mockUser?.role === 'recruiter',
      isAdmin: mockUser?.role === 'admin',
      isSuperAdmin: mockUser?.role === 'super_admin',
      hasAnyRole: (...roles: string[]) => !!mockUser && roles.includes(mockUser.role),
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

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe('Sidebar — role-based navigation (Phase 5)', () => {
  it('shows Candidate navigation for a candidate', () => {
    mockUser = makeUser('candidate');
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Interviews' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Live Interview' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Analytics' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Resume' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /recruiter dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /admin dashboard/i })).not.toBeInTheDocument();
  });

  it('shows only the Recruiter Dashboard link for a recruiter — no candidate or admin links', () => {
    mockUser = makeUser('recruiter');
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Recruiter Dashboard' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Live Interview' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Resume' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /admin dashboard/i })).not.toBeInTheDocument();
  });

  it('shows only the Admin Dashboard link for an admin — no candidate or recruiter links', () => {
    mockUser = makeUser('admin');
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Admin Dashboard' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Recruiter Dashboard' })).not.toBeInTheDocument();
  });

  it('shows every section for a super admin ("Everything")', () => {
    mockUser = makeUser('super_admin');
    renderSidebar();
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Live Interview' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Recruiter Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Admin Dashboard' })).toBeInTheDocument();
  });

  it('always shows Settings and Log out regardless of role', () => {
    mockUser = makeUser('recruiter');
    renderSidebar();
    expect(screen.getByRole('link', { name: /profile & settings/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument();
  });
});
