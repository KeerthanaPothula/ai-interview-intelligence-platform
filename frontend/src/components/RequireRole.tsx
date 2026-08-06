import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useRole } from '../context/RoleContext';
import type { Role } from '../api/types';

interface RequireRoleProps {
  roles: Role[];
  children: ReactNode;
}

/**
 * Route-level role gate — wraps an individual <Route element> inside
 * Layout (which already handles the authentication check; this only
 * handles authorization). Redirects to /unauthorized (a real 403 page,
 * not a silent blank screen or a bounce to /login) when the current
 * user's role isn't in `roles`.
 *
 * Never redirects while roleLoading is true — see RoleContext's
 * docstring for why: role is populated asynchronously after token, so
 * redirecting on role === null during that gap would flash the 403 page
 * on every authenticated page load/refresh.
 *
 * This is defense in depth, not the actual security boundary — every
 * endpoint this page calls is independently role-gated on the backend
 * (app.core.permissions), so hiding a link here only improves UX; it
 * never substitutes for the server-side check (Phase 13).
 */
export function RequireRole({ roles, children }: RequireRoleProps) {
  const { role, roleLoading } = useRole();

  if (roleLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} aria-label="Loading" />
      </div>
    );
  }

  if (role === null || !roles.includes(role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
}
