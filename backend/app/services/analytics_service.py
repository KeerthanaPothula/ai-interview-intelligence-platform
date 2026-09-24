"""Single source of per-answer scores for candidate-facing analytics.

Two genuine, non-overlapping score sources exist:

- Upload/audio flow: InterviewAnalysis, one row per AudioResponse.
- Live Interview: ConversationTurnAnalysis, one row per answered
  ConversationTurn, produced by the same evaluation_service.

Live answers are attributed to the live session's mirrored InterviewSession
(interview_service.mirror_completed_live_session). That row exists only once
the live interview has completed and is UNIQUE per live session, so a live
interview is counted exactly once and in-progress live interviews never
contribute. Voice metrics are not part of this query: live interviews have
none, and none are invented.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Subquery, select, union_all

from app.models.analysis import AudioResponse, InterviewAnalysis
from app.models.conversation import (
    LIVE_SESSION_STATUS_COMPLETED,
    ConversationTurn,
    ConversationTurnAnalysis,
    LiveInterviewSession,
)
from app.models.interview import SESSION_STATUS_COMPLETED, InterviewSession


def scored_answers(user_id: uuid.UUID | None = None) -> Subquery:
    """Every scored answer as (user_id, session_id, created_at, overall, comm,
    tech, ps, conf). Pass user_id for a candidate's own data; None means
    platform-wide (used only for the anonymous benchmark population)."""
    upload = select(
        AudioResponse.user_id.label("user_id"),
        AudioResponse.session_id.label("session_id"),
        InterviewAnalysis.created_at.label("created_at"),
        InterviewAnalysis.overall_score.label("overall"),
        InterviewAnalysis.communication_score.label("comm"),
        InterviewAnalysis.technical_score.label("tech"),
        InterviewAnalysis.problem_solving_score.label("ps"),
        InterviewAnalysis.confidence_score.label("conf"),
    ).join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)

    live = (
        select(
            InterviewSession.user_id,
            InterviewSession.id,
            ConversationTurnAnalysis.created_at,
            ConversationTurnAnalysis.overall_score,
            ConversationTurnAnalysis.communication_score,
            ConversationTurnAnalysis.technical_score,
            ConversationTurnAnalysis.problem_solving_score,
            ConversationTurnAnalysis.confidence_score,
        )
        .join(
            ConversationTurn,
            ConversationTurnAnalysis.conversation_turn_id == ConversationTurn.id,
        )
        .join(
            LiveInterviewSession,
            ConversationTurn.live_session_id == LiveInterviewSession.id,
        )
        .join(
            InterviewSession,
            InterviewSession.live_session_id == LiveInterviewSession.id,
        )
        .where(
            LiveInterviewSession.status == LIVE_SESSION_STATUS_COMPLETED,
            InterviewSession.status == SESSION_STATUS_COMPLETED,
            # Defence in depth: the mirror copies user_id, but never let a
            # mismatched row attribute one user's answers to another.
            LiveInterviewSession.user_id == InterviewSession.user_id,
        )
    )

    if user_id is not None:
        upload = upload.where(AudioResponse.user_id == user_id)
        live = live.where(InterviewSession.user_id == user_id)

    return union_all(upload, live).subquery("scored_answers")
