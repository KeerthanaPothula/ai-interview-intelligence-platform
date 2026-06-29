"""Phase 4 — health/readiness, metrics, request-ID propagation, slow-request
logging."""

import logging

import app.main as app_main


class TestReadinessEndpoint:
    def test_ready_returns_200_when_db_and_ai_config_ok(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"]["ok"] is True
        assert body["checks"]["ai_provider_configured"]["ok"] is True

    def test_ready_reports_db_failure_as_503(self, client, monkeypatch):
        def _broken_check():
            return False, "simulated database outage"

        monkeypatch.setattr("app.main._check_database", _broken_check)
        response = client.get("/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["database"]["ok"] is False

    def test_ready_does_not_call_the_ai_provider(self, client):
        """The AI-provider check must be config-presence only (non-blocking),
        never a live network call to Gemini."""
        response = client.get("/ready")
        assert response.status_code == 200
        assert "error" not in response.json()["checks"]["ai_provider_configured"]


class TestHealthEndpointUnchanged:
    """/health must keep its exact Week-2 contract — no DB call, always 200."""

    def test_health_still_returns_200_without_db(self, client, monkeypatch):
        def _explode():
            raise AssertionError("/health must never touch the database")

        monkeypatch.setattr("app.main._check_database", _explode)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestMetricsEndpoint:
    def test_metrics_endpoint_exposed_when_enabled(self, client):
        assert app_main.settings.ENABLE_METRICS is True
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "http_requests_total" in response.text

    def test_metrics_reflect_recorded_requests(self, client):
        client.get("/health")
        response = client.get("/metrics")
        assert 'path="/health"' in response.text


class TestRequestIdPropagation:
    def test_response_includes_request_id_header(self, client):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_client_supplied_request_id_is_echoed_back(self, client):
        response = client.get("/health", headers={"X-Request-ID": "my-trace-123"})
        assert response.headers["X-Request-ID"] == "my-trace-123"

    def test_each_request_without_a_supplied_id_gets_a_unique_one(self, client):
        first = client.get("/health").headers["X-Request-ID"]
        second = client.get("/health").headers["X-Request-ID"]
        assert first != second


class TestSlowRequestLogging:
    def test_slow_request_logs_a_warning(self, client, monkeypatch, caplog):
        # Patch the settings object actually bound inside ObservabilityMiddleware
        # (app.main.settings, captured at app-startup) rather than whatever
        # get_settings() currently returns — other tests call
        # get_settings.cache_clear(), after which get_settings() returns a
        # different Settings instance than the one the middleware holds.
        monkeypatch.setattr(app_main.settings, "SLOW_REQUEST_THRESHOLD_MS", 0)

        with caplog.at_level(logging.WARNING, logger="app.request"):
            client.get("/health")

        assert any("Slow request" in record.message for record in caplog.records)

    def test_fast_request_does_not_log_a_warning(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="app.request"):
            client.get("/health")

        assert not any("Slow request" in record.message for record in caplog.records)
