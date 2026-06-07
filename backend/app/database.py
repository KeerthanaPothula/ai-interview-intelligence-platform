from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# ------------------------------------------------------------------
# Engine
#
# Pool settings are only applied for PostgreSQL. SQLite (used by the
# test suite) uses a SingletonThreadPool that does not accept these
# parameters — passing them raises a TypeError at startup.
# ------------------------------------------------------------------
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_pool_kwargs: dict = (
    {}
    if _is_sqlite
    else {
        # Number of connections kept open between requests.
        "pool_size": 5,
        # Extra connections created on demand when the pool is full.
        # Total ceiling = pool_size + max_overflow = 15.
        "max_overflow": 10,
        # Issue a cheap SELECT 1 before returning a pooled connection.
        # Silently replaces stale connections caused by idle timeouts or
        # Docker network restarts — prevents cryptic OperationalErrors.
        "pool_pre_ping": True,
        # Force-replace connections older than 1 hour to avoid firewall
        # and PostgreSQL tcp_keepalive drops.
        "pool_recycle": 3600,
    }
)

engine = create_engine(
    settings.DATABASE_URL,
    # Log every SQL statement in development; silent in production.
    echo=settings.DEBUG,
    **_pool_kwargs,
)

# ------------------------------------------------------------------
# Session factory
#
# sessionmaker returns a class (not an instance). Each call to
# SessionLocal() produces a new Session bound to the engine above.
# ------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,

    # autocommit=False: every write is wrapped in an explicit
    # transaction. You must call db.commit() to persist changes.
    # This is the correct default — autocommit makes it easy to
    # accidentally persist partial state.
    autocommit=False,

    # autoflush=False: SQLAlchemy won't automatically flush pending
    # changes to the DB before a query. Controlled flushing avoids
    # surprising INSERTs mid-transaction and is easier to reason about.
    autoflush=False,

    # expire_on_commit=False: by default, SQLAlchemy marks every ORM
    # object as "expired" after a commit, meaning the next attribute
    # access triggers a SELECT to reload the data. With FastAPI, we
    # often return Pydantic schemas constructed from ORM objects after
    # a commit but while the session is still open — expiry is fine.
    # However, setting this to False makes behaviour more predictable
    # and prevents DetachedInstanceError if an object escapes the
    # session scope.
    expire_on_commit=False,
)

# ------------------------------------------------------------------
# Declarative Base
#
# All ORM model classes inherit from Base. Base.metadata holds the
# registry of every table definition — Alembic imports this object
# in alembic/env.py to detect schema changes and generate migrations.
#
# SQLAlchemy 2.x style: DeclarativeBase is a class, not a function.
# The old style was: Base = declarative_base()
# ------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ------------------------------------------------------------------
# FastAPI dependency
#
# get_db() is a generator function used with FastAPI's Depends().
# It yields one Session per HTTP request and guarantees the session
# is closed when the request finishes — even if an exception is raised.
#
# Usage in a route:
#
#   from fastapi import Depends
#   from sqlalchemy.orm import Session
#   from app.database import get_db
#
#   @router.get("/example")
#   def example(db: Session = Depends(get_db)):
#       results = db.query(MyModel).all()
#       return results
# ------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        # Execution pauses here while FastAPI runs the route handler.
        # The session is held open for the full duration of the request.
    finally:
        # Runs after the route returns (or raises). Closes the connection
        # and returns it to the pool. The finally block guarantees this
        # runs even if the route handler raises an unhandled exception.
        db.close()
