import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProfilePage } from './ProfilePage';
import { ToastProvider } from '../context/ToastContext';
import * as client from '../api/client';

const mockLogout = vi.fn();
const mockRefreshUser = vi.fn().mockResolvedValue(undefined);

const MOCK_USER = {
  id: 'user-1',
  email: 'jane@example.com',
  full_name: 'Jane Doe',
  role: 'candidate' as const,
  organization: null,
  created_at: '2026-01-01T00:00:00Z',
};

vi.mock('../context/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/AuthContext')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({
      token: 'test-token',
      user: MOCK_USER,
      userLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      register: vi.fn(),
      logout: mockLogout,
      refreshUser: mockRefreshUser,
    })),
  };
});

// Reused across tests rather than re-created per test so `mockSetTheme`
// spy calls and the mocked current theme stay in sync with each other —
// reset in beforeEach.
let mockCurrentTheme: 'light' | 'dark' = 'dark';
const mockSetTheme = vi.fn((next: 'light' | 'dark') => {
  mockCurrentTheme = next;
});

vi.mock('../context/ThemeContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../context/ThemeContext')>();
  return {
    ...actual,
    useTheme: vi.fn(() => ({
      theme: mockCurrentTheme,
      setTheme: mockSetTheme,
      toggleTheme: vi.fn(),
    })),
  };
});

function renderPage() {
  return render(
    <ToastProvider>
      <ProfilePage />
    </ToastProvider>,
  );
}

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockLogout.mockClear();
    mockRefreshUser.mockClear();
    mockSetTheme.mockClear();
    mockCurrentTheme = 'dark';
  });

  describe('Account tab', () => {
    it('renders the profile form pre-filled with the current user', () => {
      renderPage();
      expect(screen.getByLabelText('Full name')).toHaveValue('Jane Doe');
      expect(screen.getByLabelText(/^email/i)).toHaveValue('jane@example.com');
      expect(screen.getByLabelText(/^email/i)).toBeDisabled();
    });

    it('saves a profile change successfully', async () => {
      const spy = vi.spyOn(client, 'updateProfile').mockResolvedValue({
        ...MOCK_USER,
        full_name: 'Jane Updated',
      });
      renderPage();

      const input = screen.getByLabelText('Full name');
      await userEvent.clear(input);
      await userEvent.type(input, 'Jane Updated');
      await userEvent.click(screen.getByText('Save Changes'));

      await waitFor(() => {
        expect(spy).toHaveBeenCalledWith({ full_name: 'Jane Updated' }, 'test-token');
      });
      await waitFor(() => expect(mockRefreshUser).toHaveBeenCalled());
      expect(await screen.findByText('Profile updated.')).toBeTruthy();
    });

    it('rejects an empty name without calling the API', async () => {
      const spy = vi.spyOn(client, 'updateProfile');
      renderPage();

      const input = screen.getByLabelText('Full name');
      await userEvent.clear(input);
      await userEvent.type(input, '   ');
      await userEvent.click(screen.getByText('Save Changes'));

      expect(await screen.findByText('Name cannot be empty.')).toBeTruthy();
      expect(spy).not.toHaveBeenCalled();
    });

    it('shows an inline error when the save request fails', async () => {
      vi.spyOn(client, 'updateProfile').mockRejectedValue(
        new client.ApiError(422, 'full_name cannot be blank or whitespace only.'),
      );
      renderPage();

      const input = screen.getByLabelText('Full name');
      await userEvent.clear(input);
      await userEvent.type(input, 'Something');
      await userEvent.click(screen.getByText('Save Changes'));

      expect(
        await screen.findByText('full_name cannot be blank or whitespace only.'),
      ).toBeTruthy();
    });
  });

  describe('Preferences (Account tab)', () => {
    it('shows the current theme as selected', () => {
      mockCurrentTheme = 'dark';
      renderPage();

      const darkOption = screen.getByRole('radio', { name: 'Dark' });
      const lightOption = screen.getByRole('radio', { name: 'Light' });
      expect(darkOption).toHaveAttribute('aria-checked', 'true');
      expect(lightOption).toHaveAttribute('aria-checked', 'false');
    });

    it('switches the theme and shows success feedback', async () => {
      mockCurrentTheme = 'dark';
      renderPage();

      await userEvent.click(screen.getByRole('radio', { name: 'Light' }));

      expect(mockSetTheme).toHaveBeenCalledWith('light');
      expect(await screen.findByText('Theme set to Light.')).toBeTruthy();
    });

    it('does not call setTheme when the already-selected option is clicked', async () => {
      mockCurrentTheme = 'dark';
      renderPage();

      await userEvent.click(screen.getByRole('radio', { name: 'Dark' }));

      expect(mockSetTheme).not.toHaveBeenCalled();
    });

    it('shows an honest coming-soon message for notifications', () => {
      renderPage();
      expect(
        screen.getByText(/there is no notification system in the app to configure/i),
      ).toBeTruthy();
    });

    it('shows an honest coming-soon message for timezone/regional settings', () => {
      renderPage();
      expect(
        screen.getByText(/every date and time shown in the app already uses your browser/i),
      ).toBeTruthy();
    });
  });

  describe('Security tab', () => {
    async function goToSecurityTab() {
      await userEvent.click(screen.getByText('Security'));
    }

    it('changes the password successfully', async () => {
      const spy = vi.spyOn(client, 'changePassword').mockResolvedValue({
        detail: 'Password changed successfully. Please log in again.',
      });
      renderPage();
      await goToSecurityTab();

      await userEvent.type(screen.getByLabelText('Current password'), 'oldpassword1');
      await userEvent.type(screen.getByLabelText(/^new password/i), 'newpassword1');
      await userEvent.type(screen.getByLabelText('Confirm new password'), 'newpassword1');
      await userEvent.click(screen.getByRole('button', { name: 'Change Password' }));

      await waitFor(() => {
        expect(spy).toHaveBeenCalledWith(
          { current_password: 'oldpassword1', new_password: 'newpassword1' },
          'test-token',
        );
      });
      expect(
        await screen.findByText('Password changed successfully. Please log in again.'),
      ).toBeTruthy();
    });

    it('rejects a mismatched confirmation without calling the API', async () => {
      const spy = vi.spyOn(client, 'changePassword');
      renderPage();
      await goToSecurityTab();

      await userEvent.type(screen.getByLabelText('Current password'), 'oldpassword1');
      await userEvent.type(screen.getByLabelText(/^new password/i), 'newpassword1');
      await userEvent.type(screen.getByLabelText('Confirm new password'), 'different1');
      await userEvent.click(screen.getByRole('button', { name: 'Change Password' }));

      expect(await screen.findByText('New passwords do not match.')).toBeTruthy();
      expect(spy).not.toHaveBeenCalled();
    });

    it('shows an error message when the current password is wrong', async () => {
      vi.spyOn(client, 'changePassword').mockRejectedValue(
        new client.ApiError(400, 'Current password is incorrect.'),
      );
      renderPage();
      await goToSecurityTab();

      await userEvent.type(screen.getByLabelText('Current password'), 'wrongpassword');
      await userEvent.type(screen.getByLabelText(/^new password/i), 'newpassword1');
      await userEvent.type(screen.getByLabelText('Confirm new password'), 'newpassword1');
      await userEvent.click(screen.getByRole('button', { name: 'Change Password' }));

      expect(await screen.findByText('Current password is incorrect.')).toBeTruthy();
    });

    it('signs out of all sessions after confirmation', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      const spy = vi.spyOn(client, 'logoutAllSessions').mockResolvedValue({
        detail: 'Signed out of all sessions.',
      });
      renderPage();
      await goToSecurityTab();

      await userEvent.click(screen.getByText('Sign out everywhere'));

      await waitFor(() => expect(spy).toHaveBeenCalledWith('test-token'));
      await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    });

    it('does nothing if the sign-out-everywhere confirmation is declined', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(false);
      const spy = vi.spyOn(client, 'logoutAllSessions');
      renderPage();
      await goToSecurityTab();

      await userEvent.click(screen.getByText('Sign out everywhere'));

      expect(spy).not.toHaveBeenCalled();
      expect(mockLogout).not.toHaveBeenCalled();
    });
  });

  describe('Danger Zone', () => {
    it('does not offer account deletion or data export, which have no backend endpoint', () => {
      renderPage();

      expect(screen.queryByText('Danger Zone')).toBeNull();
      expect(screen.queryByRole('button', { name: 'Delete Account' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Export Data' })).toBeNull();
    });
  });
});
