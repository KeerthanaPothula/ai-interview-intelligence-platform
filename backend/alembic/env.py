import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make `app` importable when Alembic runs from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import Base

# Import every model module so SQLAlchemy registers the tables with
# Base.metadata before Alembic reads it. Missing an import here means
# Alembic silently ignores that table during autogenerate.
import app.models.user  # noqa: F401 — side-effect import

settings = get_settings()
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the blank sqlalchemy.url from alembic.ini with the real
# DATABASE_URL from settings. This is the only place the URL is resolved.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Emit SQL to stdout without a live DB connection.
    Useful for generating a migration script to review before applying.

    Run with:  alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Apply migrations against a live database connection.

    NullPool is used here so Alembic does not hold connections open
    between migration steps — migrations are infrequent and short-lived.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
