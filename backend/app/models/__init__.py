# ---------------------------------------------------------------------------
# Model registry — side-effect imports only.
#
# Importing this package causes every ORM model module to be executed,
# which registers each table definition with Base.metadata. Alembic's
# autogenerate inspects Base.metadata to produce migration files; any
# model module that has not been imported will be silently absent from
# generated migrations.
#
# Models registered by each module:
#
#   user.py      → User
#   interview.py → InterviewSession, Question
#   analysis.py  → AudioResponse, Transcript, InterviewAnalysis
#
# How to use in alembic/env.py:
#
#   import app.models  # one line discovers every table
#
# How to add a new model in the future:
#
#   1. Create app/models/<name>.py with your ORM class.
#   2. Add `from . import <name>` below.
#   3. Done — alembic/env.py discovers it automatically.
#      No other file needs to change.
#
# Import order: natural dependency order for readability.
# SQLAlchemy resolves relationship() strings lazily at mapper
# configuration time, so Python import order does not affect
# whether cross-model relationships are wired correctly.
# ---------------------------------------------------------------------------

from . import analysis, interview, user  # noqa: F401
