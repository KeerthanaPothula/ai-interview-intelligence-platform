import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function NotFoundPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="not-found-page">
      <div className="not-found-code">404</div>
      <h1 className="not-found-title">Page not found</h1>
      <p className="not-found-body">
        The page you're looking for doesn't exist or may have been moved.
      </p>
      <Link
        to={isAuthenticated ? '/dashboard' : '/'}
        className="btn btn-primary"
        style={{ marginTop: '0.5rem' }}
      >
        {isAuthenticated ? 'Back to Dashboard' : 'Back to Home'}
      </Link>
    </div>
  );
}
