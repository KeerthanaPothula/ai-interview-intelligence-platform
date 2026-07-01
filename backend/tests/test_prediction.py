"""Tests for interview readiness scoring, coaching plan, and benchmarking endpoints."""

import uuid

_MOCK_PLAN = {
    "plan_7_day": ["Day 1-2: Practice STAR method", "Day 3-5: System design review"],
    "plan_14_day": ["Week 1: Technical fundamentals", "Week 2: Mock interviews"],
    "plan_30_day": ["Week 1-2: Deep skill building", "Week 3-4: Final preparation"],
    "focus_areas": ["System Design", "Communication", "Problem Solving"],
    "model_used": "gemini-2.0-flash",
}


def _mock_readiness(
    *,
    overall_score,
    communication_score,
    technical_score,
    problem_solving_score,
    avg_confidence=60.0,
    avg_speaking_rate=130.0,
    avg_filler_words=3.0,
):
    return 0.75, "Strong"


def _mock_coaching(**kwargs):
    return _MOCK_PLAN.copy()


# ---------------------------------------------------------------------------
# POST /api/v1/interviews/{id}/readiness
# ---------------------------------------------------------------------------


def test_generate_readiness_success(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.prediction.prediction_service.compute_readiness",
        _mock_readiness,
    )

    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["session_id"] == str(interview_session.id)
    assert data["readiness_score"] == 0.75
    assert data["readiness_level"] == "Strong"
    assert "percentile_rank" in data


def test_generate_readiness_no_analyses(client, auth_headers, interview_session):
    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_generate_readiness_wrong_session(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.routers.prediction.prediction_service.compute_readiness",
        _mock_readiness,
    )
    resp = client.post(
        f"/api/v1/interviews/{uuid.uuid4()}/readiness",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_generate_readiness_requires_auth(client, interview_session):
    resp = client.post(f"/api/v1/interviews/{interview_session.id}/readiness")
    assert resp.status_code == 401


def test_generate_readiness_idempotent(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.prediction.prediction_service.compute_readiness",
        _mock_readiness,
    )
    resp1 = client.post(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    assert resp1.status_code == 201
    resp2 = client.post(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    assert resp2.status_code == 201


# ---------------------------------------------------------------------------
# GET /api/v1/interviews/{id}/readiness
# ---------------------------------------------------------------------------


def test_get_readiness_not_generated(client, auth_headers, interview_session):
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_get_readiness_after_generate(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.prediction.prediction_service.compute_readiness",
        _mock_readiness,
    )
    client.post(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/readiness",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["readiness_level"] == "Strong"


# ---------------------------------------------------------------------------
# POST /api/v1/interviews/{id}/coaching-plan
# ---------------------------------------------------------------------------


def test_generate_coaching_plan_success(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.prediction.career_coach_service.generate_coaching_plan",
        _mock_coaching,
    )
    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["session_id"] == str(interview_session.id)
    assert data["plan_7_day"] == _MOCK_PLAN["plan_7_day"]
    assert data["focus_areas"] == _MOCK_PLAN["focus_areas"]


def test_generate_coaching_plan_no_analyses(client, auth_headers, interview_session):
    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_generate_coaching_plan_wrong_session(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.routers.prediction.career_coach_service.generate_coaching_plan",
        _mock_coaching,
    )
    resp = client.post(
        f"/api/v1/interviews/{uuid.uuid4()}/coaching-plan",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_generate_coaching_plan_requires_auth(client, interview_session):
    resp = client.post(f"/api/v1/interviews/{interview_session.id}/coaching-plan")
    assert resp.status_code == 401


def test_generate_coaching_plan_idempotent(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.prediction.career_coach_service.generate_coaching_plan",
        _mock_coaching,
    )
    r1 = client.post(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    assert r1.status_code == 201

    new_plan = {**_MOCK_PLAN, "focus_areas": ["Updated Focus"]}
    monkeypatch.setattr(
        "app.routers.prediction.career_coach_service.generate_coaching_plan",
        lambda **kw: new_plan,
    )
    r2 = client.post(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    assert r2.status_code == 201
    assert r2.json()["focus_areas"] == ["Updated Focus"]


# ---------------------------------------------------------------------------
# GET /api/v1/interviews/{id}/coaching-plan
# ---------------------------------------------------------------------------


def test_get_coaching_plan_not_generated(client, auth_headers, interview_session):
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_get_coaching_plan_after_generate(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.prediction.career_coach_service.generate_coaching_plan",
        _mock_coaching,
    )
    client.post(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/coaching-plan",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["model_used"] == "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/benchmarks
# ---------------------------------------------------------------------------


def test_get_benchmarks_no_data(client, auth_headers):
    resp = client.get("/api/v1/analytics/benchmarks", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_average_score"] is None
    assert data["percentile_rank"] is None
    assert data["user_responses_analyzed"] == 0


def test_get_benchmarks_with_data(
    client, auth_headers, interview_session, interview_analysis
):
    resp = client.get("/api/v1/analytics/benchmarks", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_average_score"] is not None
    assert data["user_responses_analyzed"] == 1
    assert data["total_platform_responses"] == 1


def test_get_benchmarks_requires_auth(client):
    resp = client.get("/api/v1/analytics/benchmarks")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# prediction_service unit tests — transparent weighted formula, no ML model
# ---------------------------------------------------------------------------

_READINESS_LEVELS = {"Excellent", "Strong", "Developing", "Needs Improvement"}


def test_compute_readiness_strong_candidate():
    from app.services.prediction_service import compute_readiness

    score, level = compute_readiness(
        overall_score=9.0,
        communication_score=9.0,
        technical_score=9.0,
        problem_solving_score=9.0,
        avg_confidence=90.0,
        avg_speaking_rate=130.0,
        avg_filler_words=1.0,
    )
    assert 0.0 <= score <= 1.0
    assert level in _READINESS_LEVELS
    assert level == "Excellent"


def test_compute_readiness_weak_candidate():
    from app.services.prediction_service import compute_readiness

    score, level = compute_readiness(
        overall_score=3.0,
        communication_score=3.0,
        technical_score=3.0,
        problem_solving_score=3.0,
        avg_confidence=25.0,
        avg_speaking_rate=80.0,
        avg_filler_words=15.0,
    )
    assert 0.0 <= score <= 1.0
    assert level in _READINESS_LEVELS
    assert level == "Needs Improvement"


def test_compute_readiness_is_deterministic():
    """Same inputs always produce the same output — there is no trained model
    or randomness involved, unlike the old logistic-regression implementation."""
    from app.services.prediction_service import compute_readiness

    kwargs = dict(
        overall_score=7.0,
        communication_score=6.5,
        technical_score=7.5,
        problem_solving_score=6.0,
        avg_confidence=70.0,
        avg_filler_words=4.0,
    )
    first = compute_readiness(**kwargs)
    second = compute_readiness(**kwargs)
    assert first == second


def test_compute_percentile():
    from app.services.prediction_service import compute_percentile

    all_scores = [5.0, 6.0, 7.0, 8.0, 9.0]
    assert compute_percentile(7.0, all_scores) == 40.0
    assert compute_percentile(5.0, all_scores) == 0.0
    assert compute_percentile(10.0, all_scores) == 100.0


def test_compute_percentile_empty():
    from app.services.prediction_service import compute_percentile

    assert compute_percentile(7.0, []) == 50.0
