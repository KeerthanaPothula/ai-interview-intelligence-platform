"""OpenTelemetry tracing setup.

Disabled by default (see Settings.ENABLE_TRACING). The SDK, exporter, and
auto-instrumentation imports are deferred inside configure_tracing() so
that the (heavier) export machinery is only loaded when tracing is
actually enabled.

get_tracer() is safe to call unconditionally: when tracing was never
configured, the OpenTelemetry API returns a no-op tracer whose spans are
inert, so manual instrumentation call sites don't need their own
ENABLE_TRACING checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace

from app.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.engine import Engine


def configure_tracing(app: "FastAPI", engine: "Engine", settings: Settings) -> None:
    """Set up the global TracerProvider and instrument FastAPI + SQLAlchemy.

    No-op if settings.ENABLE_TRACING is False.
    """
    if not settings.ENABLE_TRACING:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

    resource = Resource.create({SERVICE_NAME: settings.OTEL_SERVICE_NAME})
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(settings.OTEL_TRACES_SAMPLE_RATE),
    )

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    else:
        # No collector configured — export to the console so tracing is
        # still observable locally without standing up infrastructure.
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)


def get_tracer(name: str):
    """Return a tracer for manual spans.

    Always safe to call: before configure_tracing() runs (or when tracing
    is disabled), this returns a no-op tracer from the OpenTelemetry API,
    which has no dependency on the SDK or any exporter.
    """
    return trace.get_tracer(name)
