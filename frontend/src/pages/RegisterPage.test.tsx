import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { RegisterPage } from './RegisterPage';
import { ApiError } from '../api/client';

const mockRegister = vi.fn();
let mockIsAuthenticated = false;

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: null,
      user: null,
      isAuthenticated: mockIsAuthenticated,
      login: vi.fn(),
      register: mockRegister,
      logout: vi.fn(),
    })),
  };
});

function renderRegisterPage() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  );
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/first name/i), 'Jane');
  await user.type(screen.getByLabelText(/last name/i), 'Smith');
  await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
  await user.type(screen.getByLabelText(/^password$/i), 'Password1!');
  await user.type(screen.getByLabelText(/confirm password/i), 'Password1!');
  await user.click(screen.getByLabelText(/terms of service/i));
}

beforeEach(() => {
  mockIsAuthenticated = false;
  mockRegister.mockReset();
});

describe('RegisterPage', () => {
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
    const user = userEvent.setup();
    renderRegisterPage();
    await fillValidForm(user);
    await user.clear(screen.getByLabelText(/confirm password/i));
    await user.type(screen.getByLabelText(/confirm password/i), 'Different1!');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('rejects a short password without calling register()', async () => {
    const user = userEvent.setup();
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
    const user = userEvent.setup();
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
    const user = userEvent.setup();
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
    const user = userEvent.setup();
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
    const user = userEvent.setup();
    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i);
  });

  it('redirects to /dashboard when already authenticated', () => {
    mockIsAuthenticated = true;
    renderRegisterPage();
    expect(screen.queryByLabelText(/first name/i)).not.toBeInTheDocument();
  });
});
