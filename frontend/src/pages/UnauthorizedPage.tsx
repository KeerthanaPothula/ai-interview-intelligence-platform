import { Link } from 'react-router-dom';
import { useRole } from '../context/RoleContext';
import { homeRouteForRole } from '../utils/roleRoutes';

export function UnauthorizedPage() {
  const { role } = useRole();

  return (
    <div className="not-found-page">
      <div className="not-found-code">403</div>
      <h1 className="not-found-title">You don't have access to this page</h1>
      <p className="not-found-body">
        Your account doesn't have permission to view this. If you think this is a
        mistake, contact your administrator.
      </p>
      <Link to={homeRouteForRole(role)} className="btn btn-primary" style={{ marginTop: '0.5rem' }}>
        Back to my dashboard
      </Link>
    </div>
  );
}
