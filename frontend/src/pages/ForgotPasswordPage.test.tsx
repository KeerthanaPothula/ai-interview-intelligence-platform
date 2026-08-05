import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ForgotPasswordPage } from './ForgotPasswordPage';
import * as client from '../api/client';

function renderPage() {
  return render(
    <MemoryRouter>
      <ForgotPasswordPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('ForgotPasswordPage', () => {
  it('renders the email field and submit button', () => {
    renderPage();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
  });

  it('calls forgotPassword() with the submitted email', async () => {
    vi.spyOn(client, 'forgotPassword').mockResolvedValue({ detail: 'ok' });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() =>
      expect(client.forgotPassword).toHaveBeenCalledWith({ email: 'jane@example.com' }),
    );
  });

  it('shows the same success message whether or not the account exists (no enumeration)', async () => {
    vi.spyOn(client, 'forgotPassword').mockResolvedValue({ detail: 'ok' });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/email/i), 'nonexistent@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument();
    expect(screen.getByText(/nonexistent@example.com/)).toBeInTheDocument();
  });

  it('shows an error message when the request fails', async () => {
    vi.spyOn(client, 'forgotPassword').mockRejectedValue(
      new client.ApiError(500, 'Something went wrong. Please try again.'),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/email/i), 'jane@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
