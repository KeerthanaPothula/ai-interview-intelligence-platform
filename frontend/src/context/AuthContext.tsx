import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import * as api from '../api/client';
import type { UserCreate, UserResponse } from '../api/types';

interface AuthContextValue {
  token: string | null;
  user: UserResponse | null;
  isAuthenticated: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (data: UserCreate) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => api.readStoredAccessToken());
  const [user, setUser] = useState<UserResponse | null>(null);

  const login = useCallback(async (email: string, password: string, rememberMe = true) => {
    const result = await api.login(email, password);
    api.storeTokens(result, rememberMe);
    setToken(result.access_token);
  }, []);

  const register = useCallback(async (data: UserCreate) => {
    await api.register(data);
    // Automatic login after registration, using the same credentials the
    // user just submitted. Registration itself already succeeded by this
    // point, so a failure here (network blip, etc.) is swallowed rather
    // than surfaced as a registration error — the caller (RegisterPage)
    // falls back to its own "sign in manually" screen whenever
    // isAuthenticated is still false after this resolves.
    try {
      const result = await api.login(data.email, data.password);
      api.storeTokens(result, true);
      setToken(result.access_token);
    } catch {
      // Fall through — see comment above.
    }
  }, []);

  const logout = useCallback(() => {
    api.logoutAndClearTokens();
    setToken(null);
  }, []);

  // Register the global 401 / silent-refresh hooks once on mount. These let
  // app.core's shared request() function (every API call funnels through
  // it) keep this context's React state in sync with the token actually
  // held in storage, without every page component needing its own
  // token-lifecycle handling.
  useEffect(() => {
    api.registerUnauthorizedHandler(() => {
      api.clearStoredTokens();
      setToken(null);
    });
    api.registerTokenRefreshedHandler((tokens) => {
      setToken(tokens.access_token);
    });
    return () => {
      api.registerUnauthorizedHandler(null);
      api.registerTokenRefreshedHandler(null);
    };
  }, []);

  // Load the current user's profile whenever the token changes (including
  // on initial mount, if a session was persisted) — used for the avatar
  // initials/name in TopBar. A failure here is non-fatal: if it's a 401,
  // the handler above already clears the token and this effect re-runs
  // with token === null; any other failure just leaves `user` unset.
  useEffect(() => {
    if (!token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
      setUser(null);
      return;
    }
    let cancelled = false;
    api
      .getMe(token)
      .then((fetchedUser) => {
        if (!cancelled) setUser(fetchedUser);
      })
      .catch(() => {
        // See comment above.
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, isAuthenticated: token !== null, login, register, logout }),
    [token, user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- hook is colocated with its provider
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
