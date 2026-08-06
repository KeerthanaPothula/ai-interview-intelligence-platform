import type { Role } from '../api/types';

/**
 * The default "home" route for each role — used for the post-login
 * redirect (Phase 10), the 403 page's "back to my dashboard" link, and
 * anywhere else that needs "where does this role belong by default."
 *
 * Super Admin has no dedicated dashboard of its own (Phase 4: "Super
 * Admin: Everything") — /dashboard is as reasonable a landing spot as any
 * other route it's allowed to reach.
 */
export function homeRouteForRole(role: Role | null): string {
  switch (role) {
    case 'recruiter':
      return '/recruiter';
    case 'admin':
      return '/admin';
    case 'super_admin':
    case 'candidate':
    default:
      return '/dashboard';
  }
}
