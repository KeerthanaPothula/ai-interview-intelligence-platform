import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ResetPasswordPage } from './ResetPasswordPage';
import * as client from '../api/client';

function renderPage(token = 'reset-token-123') {
  return render(
    <MemoryRouter initialEntries={[`/reset-password/${token}`]}>
      <Routes>
        <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('ResetPasswordPage', () => {
  it('renders new password and confirm password fields', () => {
    renderPage();
    expect(screen.getByLabelText("New password")).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
  });

  it('reads the token from the URL and submits it with the new password', async () => {
    vi.spyOn(client, 'resetPassword').mockResolvedValue({ detail: 'ok' });
    const user = userEvent.setup();
    renderPage('reset-token-123');

    await user.type(screen.getByLabelText("New password"), 'NewPassword1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'NewPassword1!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    await waitFor(() =>
      expect(client.resetPassword).toHaveBeenCalledWith({
        token: 'reset-token-123',
        new_password: 'NewPassword1!',
      }),
    );
  });

  it('rejects mismatched passwords without calling the API', async () => {
    const resetPasswordSpy = vi.spyOn(client, 'resetPassword');
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("New password"), 'NewPassword1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'Different1!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    expect(resetPasswordSpy).not.toHaveBeenCalled();
  });

  it('shows a success screen with a link to log in after a successful reset', async () => {
    vi.spyOn(client, 'resetPassword').mockResolvedValue({ detail: 'ok' });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("New password"), 'NewPassword1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'NewPassword1!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(await screen.findByText(/password updated/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument();
  });

  it('shows an error message for an invalid or expired token', async () => {
    vi.spyOn(client, 'resetPassword').mockRejectedValue(
      new client.ApiError(400, 'This reset link is invalid or has expired. Please request a new one.'),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText("New password"), 'NewPassword1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'NewPassword1!');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/i);
  });
});
