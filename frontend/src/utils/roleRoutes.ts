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

// Route role gates (used by App.tsx). They follow the backend's permissions
// (app/core/permissions.py), which stay the real security boundary.
// Candidate pages: can_create_interview = Candidate + Super Admin.
export const CANDIDATE_ROLES: Role[] = ['candidate', 'super_admin'];
// Candidate pipeline: can_view_candidates = Recruiter + Admin + Super Admin.
export const RECRUITER_ROLES: Role[] = ['recruiter', 'admin', 'super_admin'];
export const ADMIN_ROLES: Role[] = ['admin', 'super_admin'];
export const ANY_ROLE: Role[] = ['candidate', 'recruiter', 'admin', 'super_admin'];
// A report is readable by its owner or by anyone who can view the pipeline
// (recruiter_service.get_viewable_session_or_404).
export const REPORT_ROLES: Role[] = [...new Set([...CANDIDATE_ROLES, ...RECRUITER_ROLES])];
