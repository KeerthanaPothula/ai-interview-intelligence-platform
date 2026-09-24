"""Completed Live Interviews in candidate analytics.

Live answers are scored into ConversationTurnAnalysis (not InterviewAnalysis)
and reach analytics only through the live session's mirrored InterviewSession
— see app.services.analytics_service.scored_answers.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from app.models.conversation import (
    LIVE_SESSION_STATUS_ACTIVE,
    LIVE_SESSION_STATUS_COMPLETED,
    ConversationTurn,
    ConversationTurnAnalysis,
    LiveInterviewSession,
)
from app.models.features import VoiceAnalysis
from app.models.interview import InterviewSession
from app.services import interview_service

OVERVIEW = "/api/v1/analytics/overview"
TRENDS = "/api/v1/analytics/trends"
INSIGHTS = "/api/v1/analytics/insights"
BENCHMARKS = "/api/v1/analytics/benchmarks"


def _live(db, user_id, scores, status=LIVE_SESSION_STATUS_COMPLETED, mirror=True):
    """Create a live interview whose turns carry `scores`.

    Each item is (overall, comm, tech, ps, conf) for a scored answer, or None
    for an asked-but-unscored turn. Returns the mirrored InterviewSession (or
    None when mirror=False).
    """
    live = LiveInterviewSession(
        user_id=uuid.UUID(str(user_id)),
        job_role="Backend Engineer",
        job_description="Python backend engineering role.",
        max_turns=max(len(scores), 3),
        current_turn=max(len(scores), 1),
        status=status,
    )
    db.add(live)
    db.flush()
    for i, s in enumerate(scores, start=1):
        turn = ConversationTurn(
            live_session_id=live.id,
            turn_number=i,
            question_text=f"Question {i}",
            response_text=None if s is None else f"Answer {i}",
        )
        db.add(turn)
        db.flush()
        if s is not None:
            db.add(
                ConversationTurnAnalysis(
                    conversation_turn_id=turn.id,
                    overall_score=Decimal(str(s[0])),
                    communication_score=Decimal(str(s[1])),
                    technical_score=Decimal(str(s[2])),
                    problem_solving_score=Decimal(str(s[3])),
                    confidence_score=Decimal(str(s[4])),
                )
            )
    db.commit()
    return interview_service.mirror_completed_live_session(db, live) if mirror else None


def _bob_headers(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "password": "securepassword1",
            "full_name": "Bob",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "bob@example.com", "password": "securepassword1"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# 1 + 8: upload flow unchanged, and combined with live answers per-answer.
def test_upload_and_live_answers_are_combined(
    client, auth_headers, db, registered_user, interview_session, interview_analysis
):
    # Upload answer: overall 7.5 (fixture). Live answer: overall 9.5, later.
    _live(db, registered_user["id"], [(9.5, 9.0, 9.0, 9.0, 9.0)])
    db.query(ConversationTurnAnalysis).update(
        {"created_at": interview_analysis.created_at + timedelta(days=1)}
    )
    db.commit()

    data = client.get(OVERVIEW, headers=auth_headers).json()
    assert set(data) == {
        "total_sessions",
        "completed_sessions",
        "average_overall_score",
        "total_responses_analyzed",
        "strongest_skill",
        "weakest_skill",
        "improvement_score",
    }
    assert data["total_sessions"] == 2
    assert data["completed_sessions"] == 1
    assert data["total_responses_analyzed"] == 2
    assert data["average_overall_score"] == 8.5
    assert data["improvement_score"] == 2.0  # 9.5 (latest) - 7.5 (first)

    trends = {
        t["session_id"]: t for t in client.get(TRENDS, headers=auth_headers).json()
    }
    assert trends[str(interview_session.id)]["average_overall_score"] == 7.5


# 2 + 3 + 10: genuine live scores, several answers averaged.
def test_completed_live_interview_scores_are_averaged(
    client, auth_headers, db, registered_user
):
    _live(
        db,
        registered_user["id"],
        [(6.0, 9.0, 5.0, 6.0, 7.0), (9.0, 8.0, 6.0, 7.0, 8.0)],
    )

    data = client.get(OVERVIEW, headers=auth_headers).json()
    assert data["total_responses_analyzed"] == 2
    assert data["average_overall_score"] == 7.5
    assert data["strongest_skill"] == "Communication"  # 8.5
    assert data["weakest_skill"] == "Technical"  # 5.5
    assert data["improvement_score"] is not None


# 9 + 10: trends carry the mirrored session with its real averages.
def test_trends_include_completed_live_interview(
    client, auth_headers, db, registered_user
):
    mirrored = _live(
        db,
        registered_user["id"],
        [(6.0, 9.0, 5.0, 6.0, 7.0), (9.0, 8.0, 6.0, 7.0, 8.0), None],
    )

    trends = client.get(TRENDS, headers=auth_headers).json()
    assert len(trends) == 1
    t = trends[0]
    assert set(t) == {
        "session_id",
        "session_title",
        "created_at",
        "average_overall_score",
        "average_communication_score",
        "average_technical_score",
        "average_problem_solving_score",
        "average_confidence_score",
    }
    assert t["session_id"] == str(mirrored.id)
    assert t["average_overall_score"] == 7.5
    assert t["average_communication_score"] == 8.5
    assert t["average_technical_score"] == 5.5
    assert t["average_problem_solving_score"] == 6.5
    assert t["average_confidence_score"] == 7.5


# 4: completed but nothing scored → no fabricated numbers.
def test_live_interview_without_scored_answers_does_not_contribute(
    client, auth_headers, db, registered_user
):
    _live(db, registered_user["id"], [None, None])

    data = client.get(OVERVIEW, headers=auth_headers).json()
    assert data["completed_sessions"] == 1
    assert data["total_responses_analyzed"] == 0
    assert data["average_overall_score"] is None
    assert data["strongest_skill"] is None

    [t] = client.get(TRENDS, headers=auth_headers).json()
    assert t["average_overall_score"] is None
    assert t["average_confidence_score"] is None

    assert (
        client.get(BENCHMARKS, headers=auth_headers).json()["user_responses_analyzed"]
        == 0
    )


# 5: an in-progress live interview already has scored turns (next_question
# scores each answer), but must not count until the interview completes.
def test_in_progress_live_interview_does_not_contribute(
    client, auth_headers, db, registered_user
):
    _live(
        db,
        registered_user["id"],
        [(9.0, 9.0, 9.0, 9.0, 9.0)],
        status=LIVE_SESSION_STATUS_ACTIVE,
        mirror=False,
    )

    assert (
        client.get(OVERVIEW, headers=auth_headers).json()["total_responses_analyzed"]
        == 0
    )
    assert client.get(TRENDS, headers=auth_headers).json() == []
    assert (
        client.get(BENCHMARKS, headers=auth_headers).json()["total_platform_responses"]
        == 0
    )


# 11: drafts stay in trends only as unscored rows, so goal/skill logic
# (which requires a score) can't count them.
def test_draft_session_appears_unscored(
    client, auth_headers, db, registered_user, interview_session
):
    _live(db, registered_user["id"], [(8.0, 8.0, 8.0, 8.0, 8.0)])

    trends = {
        t["session_id"]: t for t in client.get(TRENDS, headers=auth_headers).json()
    }
    assert len(trends) == 2
    assert trends[str(interview_session.id)]["average_overall_score"] is None
    assert (
        client.get(OVERVIEW, headers=auth_headers).json()["total_responses_analyzed"]
        == 1
    )


# 6: the mirror is idempotent and the live answers are counted exactly once.
def test_mirrored_live_session_is_not_double_counted(
    client, auth_headers, db, registered_user
):
    mirrored = _live(
        db,
        registered_user["id"],
        [(7.0, 7.0, 7.0, 7.0, 7.0), (8.0, 8.0, 8.0, 8.0, 8.0)],
    )
    live = db.get(LiveInterviewSession, mirrored.live_session_id)
    assert interview_service.mirror_completed_live_session(db, live).id == mirrored.id
    assert (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == live.id)
        .count()
        == 1
    )

    assert (
        client.get(OVERVIEW, headers=auth_headers).json()["total_responses_analyzed"]
        == 2
    )
    assert len(client.get(TRENDS, headers=auth_headers).json()) == 1
    bench = client.get(BENCHMARKS, headers=auth_headers).json()
    assert bench["user_responses_analyzed"] == 2
    assert bench["total_platform_responses"] == 2


# 7: per-user isolation across every candidate analytics endpoint.
def test_users_cannot_see_each_others_live_analytics(
    client, auth_headers, db, registered_user
):
    _live(db, registered_user["id"], [(8.0, 8.0, 8.0, 8.0, 8.0)])
    bob = _bob_headers(client)

    overview = client.get(OVERVIEW, headers=bob).json()
    assert overview["total_sessions"] == 0
    assert overview["total_responses_analyzed"] == 0
    assert client.get(TRENDS, headers=bob).json() == []
    bench = client.get(BENCHMARKS, headers=bob).json()
    assert bench["user_responses_analyzed"] == 0
    assert bench["user_average_score"] is None
    assert client.get(INSIGHTS, headers=bob).json()["insights"][0]["kind"] == "info"

    # Alice's own view is unaffected.
    assert (
        client.get(OVERVIEW, headers=auth_headers).json()["total_responses_analyzed"]
        == 1
    )


def test_benchmark_ranks_live_answers_against_platform(
    client, auth_headers, db, registered_user
):
    bob = _bob_headers(client)
    bob_id = client.get("/api/v1/auth/me", headers=bob).json()["id"]
    _live(db, registered_user["id"], [(9.0, 9.0, 9.0, 9.0, 9.0)])
    _live(db, bob_id, [(5.0, 5.0, 5.0, 5.0, 5.0)])

    bench = client.get(BENCHMARKS, headers=auth_headers).json()
    assert set(bench) == {
        "user_average_score",
        "percentile_rank",
        "total_platform_responses",
        "user_responses_analyzed",
    }
    assert bench["user_average_score"] == 9.0
    assert bench["user_responses_analyzed"] == 1
    assert bench["total_platform_responses"] == 2
    assert bench["percentile_rank"] is not None


def test_insights_use_live_scores(client, auth_headers, db, registered_user):
    _live(db, registered_user["id"], [(8.5, 9.0, 8.0, 8.0, 8.0)])

    texts = [
        i["text"] for i in client.get(INSIGHTS, headers=auth_headers).json()["insights"]
    ]
    assert any("8.5/10" in t for t in texts)
    assert any(t.startswith("Communication is your strongest area") for t in texts)


# 12: live interviews have no audio, so no voice metrics may appear.
def test_live_analytics_do_not_fabricate_voice_metrics(
    client, auth_headers, db, registered_user
):
    _live(db, registered_user["id"], [(8.0, 8.0, 8.0, 8.0, 6.0)])

    for url in (OVERVIEW, TRENDS, INSIGHTS, BENCHMARKS):
        assert client.get(url, headers=auth_headers).status_code == 200
    assert db.query(VoiceAnalysis).count() == 0
    # Confidence in trends is the evaluator's answer score, not a voice metric.
    assert (
        client.get(TRENDS, headers=auth_headers).json()[0]["average_confidence_score"]
        == 6.0
    )


# End to end through the real endpoints: answer scored by next_question,
# final answer scored by end, both visible on the dashboard afterwards.
def test_live_interview_via_api_appears_in_dashboard(client, auth_headers, monkeypatch):
    scores = iter([6.0, 8.0])

    def _eval(**kwargs):
        s = next(scores)
        return {
            "overall_score": s,
            "communication_score": s,
            "technical_score": s,
            "problem_solving_score": s,
            "confidence_score": s,
            "strengths": "[]",
            "weaknesses": "[]",
            "detailed_feedback": "ok",
            "model_used": "gemini-test-model",
        }

    for name, fn in {
        "app.services.interview_conversation_service.generate_opening_question": (
            lambda **kw: "Tell me about yourself."
        ),
        "app.services.interview_conversation_service.generate_follow_up_question": (
            lambda **kw: ("What would you change?", 2)
        ),
        "app.services.interview_conversation_service.generate_interview_summary": (
            lambda **kw: "Solid."
        ),
        "app.services.evaluation_service.generate_evaluation": _eval,
    }.items():
        monkeypatch.setattr(name, fn)

    sid = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    ).json()["id"]

    client.post(
        f"/api/v1/live-interviews/{sid}/next-question",
        json={"response_text": "First answer."},
        headers=auth_headers,
    )
    # Mid-interview: scored turn exists but the interview isn't complete.
    assert (
        client.get(OVERVIEW, headers=auth_headers).json()["total_responses_analyzed"]
        == 0
    )

    end = client.post(
        f"/api/v1/live-interviews/{sid}/end",
        json={"response_text": "Final answer."},
        headers=auth_headers,
    )
    assert end.status_code == 200, end.text

    data = client.get(OVERVIEW, headers=auth_headers).json()
    assert data["completed_sessions"] == 1
    assert data["total_responses_analyzed"] == 2
    assert data["average_overall_score"] == 7.0
