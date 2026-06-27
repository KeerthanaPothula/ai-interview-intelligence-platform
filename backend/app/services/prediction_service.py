"""Interview success prediction — logistic regression on synthetic training data.

The model is trained once at module import time on 2000 synthetic samples.
No external data or file download is required.
"""

from __future__ import annotations

import json
import logging
import random

logger = logging.getLogger(__name__)

_MODEL_VERSION = "lr-v1-synthetic"
_clf = None
_scaler = None


def _build_model():
    """Train a logistic regression model on synthetic interview data."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    rng = random.Random(42)
    n = 2000
    features = []
    labels = []

    for _ in range(n):
        overall = rng.uniform(3.0, 10.0)
        comm = rng.uniform(3.0, 10.0)
        tech = rng.uniform(2.0, 10.0)
        problem = rng.uniform(2.0, 10.0)
        confidence = rng.uniform(20, 100)
        speaking_rate = rng.uniform(80, 200)
        fillers = rng.uniform(0, 20)

        noise = rng.gauss(0, 0.5)
        score = (
            0.30 * overall
            + 0.20 * comm
            + 0.25 * tech
            + 0.15 * problem
            + 0.05 * (confidence / 10)
            - 0.05 * (fillers / 5)
            + noise
        )
        labels.append(1 if score >= 5.5 else 0)
        features.append(
            [overall, comm, tech, problem, confidence, speaking_rate, fillers]
        )

    X = np.array(features, dtype=np.float32)
    y = np.array(labels, dtype=np.int32)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = LogisticRegression(max_iter=500, random_state=42)
    clf.fit(X_scaled, y)

    logger.info("Prediction model trained: %s (n=%d)", _MODEL_VERSION, n)
    return clf, scaler


def _get_model():
    global _clf, _scaler
    if _clf is None:
        _clf, _scaler = _build_model()
    return _clf, _scaler


def predict_success(
    *,
    overall_score: float,
    communication_score: float,
    technical_score: float,
    problem_solving_score: float,
    avg_confidence: float = 60.0,
    avg_speaking_rate: float = 130.0,
    avg_filler_words: float = 3.0,
) -> tuple[float, str]:
    """Return (success_probability, predicted_outcome).

    Outcomes: 'Strong Pass', 'Pass', 'Borderline', 'Fail'
    """
    import numpy as np

    clf, scaler = _get_model()
    features = np.array(
        [
            [
                overall_score,
                communication_score,
                technical_score,
                problem_solving_score,
                avg_confidence,
                avg_speaking_rate,
                avg_filler_words,
            ]
        ],
        dtype=np.float32,
    )
    features_scaled = scaler.transform(features)
    prob = float(clf.predict_proba(features_scaled)[0][1])

    if prob >= 0.80:
        outcome = "Strong Pass"
    elif prob >= 0.60:
        outcome = "Pass"
    elif prob >= 0.40:
        outcome = "Borderline"
    else:
        outcome = "Fail"

    return prob, outcome


def compute_percentile(user_score: float, all_scores: list[float]) -> float:
    """Return percentile rank (0-100) of user_score relative to all_scores."""
    if not all_scores:
        return 50.0
    below = sum(1 for s in all_scores if s < user_score)
    return compute_percentile_from_counts(below, len(all_scores))


def compute_percentile_from_counts(below: int, total: int) -> float:
    """Return percentile rank (0-100) given a precomputed below/total count.

    Lets callers compute `below` and `total` via a SQL aggregate (COUNT)
    instead of fetching every row into Python just to count them.
    """
    if not total:
        return 50.0
    return round(100.0 * below / total, 1)
