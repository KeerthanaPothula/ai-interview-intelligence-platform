import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { ApiError } from '../api/client';

const mockLogin = vi.fn();
let mockIsAuthenticated = false;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: null,
      user: null,
      isAuthenticated: mockIsAuthenticated,
      login: mockLogin,
      register: vi.fn(),
      logout: vi.fn(),
    })),
  };
});

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockIsAuthenticated = false;
  mockLogin.mockReset();
});

describe('LoginPage', () => {
  it('renders email, password, remember me, and forgot password link', () => {
    renderLoginPage();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/remember me/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /forgot password/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('remember me is checked by default', () => {
    renderLoginPage();
    expect(screen.getByLabelText(/remember me/i)).toBeChecked();
  });

  it('toggles password visibility', async () => {
    const user = userEvent.setup();
    renderLoginPage();
    const passwordInput = screen.getByLabelText(/^password$/i);
    expect(passwordInput).toHaveAttribute('type', 'password');

    await user.click(screen.getByRole('button', { name: /show password/i }));
    expect(passwordInput).toHaveAttribute('type', 'text');

    await user.click(screen.getByRole('button', { name: /hide password/i }));
    expect(passwordInput).toHaveAttribute('type', 'password');
  });

  it('submits credentials and rememberMe to login()', async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith('jane@example.com', 'password123', true),
    );
  });

  it('submits rememberMe=false when unchecked', async () => {
    mockLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.click(screen.getByLabelText(/remember me/i));
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith('jane@example.com', 'password123', false),
    );
  });

  it('shows a loading spinner while submitting', async () => {
    let resolveLogin: () => void = () => {};
    mockLogin.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveLogin = resolve;
      }),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
    resolveLogin();
  });

  it('shows the backend\'s actual error message on a failed login (401)', async () => {
    // client.ts's extractErrorMessage now surfaces the backend's own
    // `detail` for 4xx responses instead of a generic per-status string —
    // LoginPage just passes err.message through verbatim.
    mockLogin.mockRejectedValue(new ApiError(401, 'Incorrect email or password.'));
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'wrong-password');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.');
  });

  it('shows the backend\'s actual error message when the account is locked (423)', async () => {
    mockLogin.mockRejectedValue(
      new ApiError(
        423,
        'Account temporarily locked due to multiple failed login attempts. Please try again later.',
      ),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/temporarily locked/i);
  });

  it('redirects to /dashboard when already authenticated', () => {
    mockIsAuthenticated = true;
    renderLoginPage();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
  });
});
