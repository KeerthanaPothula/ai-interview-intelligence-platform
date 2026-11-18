import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RegisterPage } from './RegisterPage';
import { ApiError } from '../api/client';

const mockRegister = vi.fn();
let mockIsAuthenticated = false;
let mockUserLoading = false;
let mockUser: { role: string } | null = null;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: null,
      user: mockUser,
      userLoading: mockUserLoading,
      isAuthenticated: mockIsAuthenticated,
      login: vi.fn(),
      register: mockRegister,
      logout: vi.fn(),
    })),
  };
});

// delay: null — userEvent's default (delay: 0) awaits a real setTimeout(0)
// after every keystroke. RegisterPage has no timer-driven behavior, so those
// waits test nothing, yet at ~14ms each (Windows timer resolution) they were
// most of each test's runtime and, stretched under full-suite CPU load, made
// the longest test hit its 5s timeout. Every keystroke still dispatches its
// full event sequence and re-renders.
function setupUser() {
  return userEvent.setup({ delay: null });
}

function renderRegisterPage() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  );
}

async function fillValidForm(user: ReturnType<typeof setupUser>) {
  await user.type(screen.getByLabelText(/first name/i), 'Jane');
  await user.type(screen.getByLabelText(/last name/i), 'Smith');
  await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
  await user.type(screen.getByLabelText(/^password$/i), 'Password1!');
  await user.type(screen.getByLabelText(/confirm password/i), 'Password1!');
  await user.click(screen.getByLabelText(/terms of service/i));
}

beforeEach(() => {
  mockIsAuthenticated = false;
  mockUserLoading = false;
  mockUser = null;
  mockRegister.mockReset();
});

describe('RegisterPage', () => {
  it('renders the form immediately while a stored session is still being verified', () => {
    // Regression: Get Started → /register with a saved token used to show a
    // full-page spinner until /auth/me answered (≈30 s on a cold backend).
    mockUserLoading = true;
    renderRegisterPage();
    expect(screen.getByRole('button', { name: /create account/i })).toBeEnabled();
  });

  it('renders first name, last name, email, password, confirm, and terms checkbox', () => {
    renderRegisterPage();
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/terms of service/i)).toBeInTheDocument();
  });

  it('rejects mismatched passwords without calling register()', async () => {
    const user = setupUser();
    renderRegisterPage();
    await fillValidForm(user);
    await user.clear(screen.getByLabelText(/confirm password/i));
    await user.type(screen.getByLabelText(/confirm password/i), 'Different1!');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('rejects a short password without calling register()', async () => {
    const user = setupUser();
    renderRegisterPage();
    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Smith');
    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'short1');
    await user.type(screen.getByLabelText(/confirm password/i), 'short1');
    await user.click(screen.getByLabelText(/terms of service/i));
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/at least 8 characters/i);
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('requires accepting the terms before submitting', async () => {
    const user = setupUser();
    renderRegisterPage();
    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Smith');
    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'Password1!');
    await user.type(screen.getByLabelText(/confirm password/i), 'Password1!');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/accept the terms/i);
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('combines first and last name into full_name on submit', async () => {
    mockRegister.mockResolvedValue(undefined);
    const user = setupUser();
    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() =>
      expect(mockRegister).toHaveBeenCalledWith({
        email: 'jane@example.com',
        password: 'Password1!',
        full_name: 'Jane Smith',
      }),
    );
  });

  it('shows the manual sign-in success screen when auto-login did not happen', async () => {
    mockRegister.mockResolvedValue(undefined);
    const user = setupUser();
    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByText(/account created/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in now/i })).toBeInTheDocument();
  });

  it('shows an error message when registration fails', async () => {
    mockRegister.mockRejectedValue(
      new ApiError(409, 'An account with this email already exists.'),
    );
    const user = setupUser();
    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i);
  });

  it.each([
    ['candidate', '/dashboard'],
    ['recruiter', '/recruiter'],
    ['admin', '/admin'],
  ])('redirects an authenticated %s to %s', (role, home) => {
    mockIsAuthenticated = true;
    mockUser = { role };
    render(
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path={home} element={<p>home:{home}</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText(`home:${home}`)).toBeInTheDocument();
  });
});
