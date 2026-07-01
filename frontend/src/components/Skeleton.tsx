interface SkeletonProps {
  width?: string;
  height?: string;
  className?: string;
}

export function Skeleton({ width = '100%', height = '1rem', className = '' }: SkeletonProps) {
  return (
    <span
      className={`skeleton ${className}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function SessionCardSkeleton() {
  return (
    <div className="session-card session-card-skeleton" aria-hidden="true">
      <Skeleton width="70%" height="1.1rem" />
      <Skeleton width="50%" height="0.9rem" className="skeleton-spaced" />
      <Skeleton width="40%" height="1.3rem" />
    </div>
  );
}

export function SessionListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="session-grid" aria-hidden="true" data-testid="session-list-skeleton">
      {Array.from({ length: count }, (_, i) => (
        <SessionCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function ResponseResultsSkeleton() {
  return (
    <div className="response-results-skeleton" aria-hidden="true" data-testid="response-results-skeleton">
      <Skeleton width="100%" height="4.5rem" />
      <Skeleton width="100%" height="3rem" className="skeleton-spaced" />
    </div>
  );
}

export function StatGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="stat-grid" aria-hidden="true" data-testid="stat-grid-skeleton">
      {Array.from({ length: count }, (_, i) => (
        <div className="stat-card" key={i}>
          <Skeleton width="60%" height="1.75rem" className="skeleton-center" />
          <Skeleton width="80%" height="0.8rem" className="skeleton-spaced skeleton-center" />
        </div>
      ))}
    </div>
  );
}
