"""Benchmark service — percentile rankings across all users."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services import analytics_service, prediction_service


def get_user_benchmark(user_id: uuid.UUID, db: Session) -> dict:
    """Compute the current user's percentile rank vs all platform users.

    Uses SQL aggregates (COUNT/AVG) throughout instead of fetching every
    scored answer on the platform into Python. Both the user's average and
    the platform population come from analytics_service.scored_answers(), so
    upload answers and completed Live Interview answers are ranked on the
    same footing. Only aggregate counts leave this function.
    """
    platform = analytics_service.scored_answers()
    total_count = db.execute(select(func.count()).select_from(platform)).scalar_one()

    mine = analytics_service.scored_answers(user_id)
    user_avg_raw, user_count = db.execute(
        select(func.avg(mine.c.overall), func.count()).select_from(mine)
    ).one()

    if not user_count:
        return {
            "user_average_score": None,
            "percentile_rank": None,
            "total_platform_responses": total_count,
            "user_responses_analyzed": 0,
        }

    user_avg = round(float(user_avg_raw), 2)

    below_count = db.execute(
        select(func.count()).select_from(platform).where(platform.c.overall < user_avg)
    ).scalar_one()

    percentile = prediction_service.compute_percentile_from_counts(
        below_count, total_count
    )

    return {
        "user_average_score": user_avg,
        "percentile_rank": percentile,
        "total_platform_responses": total_count,
        "user_responses_analyzed": user_count,
    }
