import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useAuth } from './AuthContext';
import type { Role } from '../api/types';

interface RoleContextValue {
  role: Role | null;
  // True while the role is not yet known (see AuthContext.userLoading) —
  // distinct from role === null, which means "known to be logged out."
  // Consumers (RequireRole, Sidebar) must treat these differently: a
  // loading role should render nothing/a spinner, never redirect.
  roleLoading: boolean;
  isCandidate: boolean;
  isRecruiter: boolean;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  hasAnyRole: (...roles: Role[]) => boolean;
}

const RoleContext = createContext<RoleContextValue | undefined>(undefined);

export function RoleProvider({ children }: { children: ReactNode }) {
  const { user, userLoading } = useAuth();
  const role = user?.role ?? null;

  const value = useMemo<RoleContextValue>(
    () => ({
      role,
      roleLoading: userLoading,
      isCandidate: role === 'candidate',
      isRecruiter: role === 'recruiter',
      isAdmin: role === 'admin',
      isSuperAdmin: role === 'super_admin',
      hasAnyRole: (...roles: Role[]) => role !== null && roles.includes(role),
    }),
    [role, userLoading],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- hook is colocated with its provider
export function useRole(): RoleContextValue {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error('useRole must be used within a RoleProvider');
  }
  return context;
}
