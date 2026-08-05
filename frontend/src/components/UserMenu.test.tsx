import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { UserMenu } from './UserMenu';

const mockLogout = vi.fn();
let mockUser: { full_name: string; email: string } | null = {
  full_name: 'Jane Smith',
  email: 'jane@example.com',
};

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: 'test-token',
      user: mockUser,
      isAuthenticated: true,
      login: vi.fn(),
      register: vi.fn(),
      logout: mockLogout,
    })),
  };
});

function renderMenu() {
  return render(
    <MemoryRouter>
      <UserMenu />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockLogout.mockReset();
  mockUser = { full_name: 'Jane Smith', email: 'jane@example.com' };
});

describe('UserMenu', () => {
  it('shows initials derived from the user\'s full name', () => {
    renderMenu();
    expect(screen.getByRole('button', { name: /profile menu/i })).toHaveTextContent('JS');
  });

  it('falls back to the email initial when no user is loaded yet', () => {
    mockUser = null;
    renderMenu();
    expect(screen.getByRole('button', { name: /profile menu/i })).toHaveTextContent('?');
  });

  it('opens the menu on click, showing the user\'s name, email, Profile, and Logout', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /profile menu/i }));

    expect(await screen.findByText('Jane Smith')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /profile/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /log out/i })).toBeInTheDocument();
  });

  it('calls logout() when "Log out" is clicked', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    await user.click(screen.getByRole('menuitem', { name: /log out/i }));

    expect(mockLogout).toHaveBeenCalled();
  });

  it('closes the menu on Escape', async () => {
    const user = userEvent.setup();
    renderMenu();

    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(await screen.findByRole('menu')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('closes the menu on outside click', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <div>
          <UserMenu />
          <button type="button">Outside</button>
        </div>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: /profile menu/i }));
    expect(await screen.findByRole('menu')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Outside' }));
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });
});
