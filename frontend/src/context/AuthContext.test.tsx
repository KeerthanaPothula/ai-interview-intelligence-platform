import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/client';
import { AuthProvider, useAuth } from './AuthContext';

const MOCK_USER = {
  id: 'user-1',
  email: 'jane@example.com',
  full_name: 'Jane Smith',
  created_at: '2026-01-01T00:00:00Z',
};

const MOCK_TOKEN = {
  access_token: 'access-123',
  refresh_token: 'refresh-456',
  token_type: 'bearer',
};

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'readStoredAccessToken').mockReturnValue(null);
  vi.spyOn(api, 'storeTokens').mockImplementation(() => {});
  vi.spyOn(api, 'clearStoredTokens').mockImplementation(() => {});
  vi.spyOn(api, 'logoutAndClearTokens').mockImplementation(() => {});
  vi.spyOn(api, 'registerUnauthorizedHandler').mockImplementation(() => {});
  vi.spyOn(api, 'registerTokenRefreshedHandler').mockImplementation(() => {});
  vi.spyOn(api, 'getMe').mockResolvedValue(MOCK_USER);
});

describe('AuthContext', () => {
  it('starts unauthenticated when no token is stored', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });

  it('restores an authenticated session from stored tokens on mount', async () => {
    vi.spyOn(api, 'readStoredAccessToken').mockReturnValue('stored-token');
    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('stored-token');

    await waitFor(() => expect(result.current.user).toEqual(MOCK_USER));
  });

  it('login() stores tokens and flips isAuthenticated', async () => {
    vi.spyOn(api, 'login').mockResolvedValue(MOCK_TOKEN);
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login('jane@example.com', 'password123', true);
    });

    expect(api.login).toHaveBeenCalledWith('jane@example.com', 'password123');
    expect(api.storeTokens).toHaveBeenCalledWith(MOCK_TOKEN, true);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('access-123');
  });

  it('login() with rememberMe=false still authenticates, using session storage', async () => {
    vi.spyOn(api, 'login').mockResolvedValue(MOCK_TOKEN);
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login('jane@example.com', 'password123', false);
    });

    expect(api.storeTokens).toHaveBeenCalledWith(MOCK_TOKEN, false);
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('login() failure leaves the user unauthenticated', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new api.ApiError(401, 'Incorrect email or password.'));
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(
      act(async () => {
        await result.current.login('jane@example.com', 'wrong-password');
      }),
    ).rejects.toThrow();

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
  });

  it('register() auto-logs-in with the same credentials on success', async () => {
    vi.spyOn(api, 'register').mockResolvedValue(MOCK_USER);
    vi.spyOn(api, 'login').mockResolvedValue(MOCK_TOKEN);
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.register({
        email: 'jane@example.com',
        password: 'password123',
        full_name: 'Jane Smith',
      });
    });

    expect(api.register).toHaveBeenCalled();
    expect(api.login).toHaveBeenCalledWith('jane@example.com', 'password123');
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('register() failure does not attempt auto-login', async () => {
    vi.spyOn(api, 'register').mockRejectedValue(
      new api.ApiError(409, 'An account with this email already exists.'),
    );
    const loginSpy = vi.spyOn(api, 'login');
    const { result } = renderHook(() => useAuth(), { wrapper });

    await expect(
      act(async () => {
        await result.current.register({
          email: 'jane@example.com',
          password: 'password123',
          full_name: 'Jane Smith',
        });
      }),
    ).rejects.toThrow();

    expect(loginSpy).not.toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('register() succeeding but auto-login failing leaves the user unauthenticated without throwing', async () => {
    vi.spyOn(api, 'register').mockResolvedValue(MOCK_USER);
    vi.spyOn(api, 'login').mockRejectedValue(new Error('network blip'));
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.register({
        email: 'jane@example.com',
        password: 'password123',
        full_name: 'Jane Smith',
      });
    });

    expect(result.current.isAuthenticated).toBe(false);
  });

  it('logout() clears the session', async () => {
    vi.spyOn(api, 'login').mockResolvedValue(MOCK_TOKEN);
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login('jane@example.com', 'password123');
    });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      result.current.logout();
    });

    expect(api.logoutAndClearTokens).toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });

  it('registers a global unauthorized handler that clears the session when invoked', async () => {
    vi.spyOn(api, 'login').mockResolvedValue(MOCK_TOKEN);
    let capturedHandler: (() => void) | null = null;
    vi.spyOn(api, 'registerUnauthorizedHandler').mockImplementation((handler) => {
      capturedHandler = handler;
    });

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login('jane@example.com', 'password123');
    });
    expect(result.current.isAuthenticated).toBe(true);

    expect(capturedHandler).not.toBeNull();
    act(() => {
      capturedHandler?.();
    });

    expect(api.clearStoredTokens).toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('registers a token-refreshed handler that updates the stored access token', async () => {
    let capturedHandler: ((tokens: typeof MOCK_TOKEN) => void) | null = null;
    vi.spyOn(api, 'registerTokenRefreshedHandler').mockImplementation((handler) => {
      capturedHandler = handler as (tokens: typeof MOCK_TOKEN) => void;
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(capturedHandler).not.toBeNull();

    act(() => {
      capturedHandler?.({ ...MOCK_TOKEN, access_token: 'refreshed-access-token' });
    });

    expect(result.current.token).toBe('refreshed-access-token');
    expect(result.current.isAuthenticated).toBe(true);
  });
});
