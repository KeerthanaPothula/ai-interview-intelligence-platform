from app.config import Settings


# ---------------------------------------------------------------------------
# CORS_ORIGINS parsing
#
# CORS_ORIGINS is declared as `str | list[str]` with a
# field_validator(mode="before") that splits a comma-separated string into a
# list of trimmed, non-empty origins. Passing CORS_ORIGINS as an init kwarg
# (instead of via the environment) exercises this validator directly while
# keeping the test independent of any .env file or process environment.
# ---------------------------------------------------------------------------


def _settings_with_cors(cors_origins: str) -> Settings:
    return Settings(
        DATABASE_URL="sqlite:///./test.db",
        JWT_SECRET_KEY="x" * 32,
        GEMINI_API_KEY="test-key",
        CORS_ORIGINS=cors_origins,
    )


class TestCorsOriginsParsing:
    def test_parse_single_cors_origin(self):
        settings = _settings_with_cors("https://example.com")
        assert settings.CORS_ORIGINS == ["https://example.com"]

    def test_parse_multiple_cors_origins(self):
        settings = _settings_with_cors("http://localhost:3000,http://localhost:5173")
        assert settings.CORS_ORIGINS == [
            "http://localhost:3000",
            "http://localhost:5173",
        ]

    def test_parse_cors_origins_trims_whitespace(self):
        settings = _settings_with_cors(" http://localhost:3000 , https://example.com ")
        assert settings.CORS_ORIGINS == [
            "http://localhost:3000",
            "https://example.com",
        ]

    def test_empty_entries_removed(self):
        settings = _settings_with_cors("http://localhost:3000,,https://example.com,")
        assert settings.CORS_ORIGINS == [
            "http://localhost:3000",
            "https://example.com",
        ]
