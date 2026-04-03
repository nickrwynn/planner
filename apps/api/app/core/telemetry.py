from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def setup_telemetry(app, *, service_name: str = "academic-os-api") -> None:
    """Best-effort OpenTelemetry setup; no-op if deps are missing."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as e:  # noqa: BLE001
        logger.warning("telemetry disabled: missing opentelemetry deps (%s)", e)
        return

    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


def emit_diagnostic(event: str, *, level: str = "info", **fields) -> None:
    service_name = str(fields.get("service") or fields.get("service_name") or "api")
    normalized_level = level.lower().strip() or "info"
    if normalized_level == "warn":
        normalized_level = "warning"
    normalized_fields = {
        key: value
        for key, value in fields.items()
        if key not in {"service", "service_name"} and value is not None
    }
    if not normalized_fields.get("correlation_id"):
        if normalized_fields.get("job_id"):
            normalized_fields["correlation_id"] = f"job:{normalized_fields['job_id']}"
        elif normalized_fields.get("resource_id"):
            normalized_fields["correlation_id"] = f"resource:{normalized_fields['resource_id']}"
        elif normalized_fields.get("dead_letter_id"):
            normalized_fields["correlation_id"] = f"dead_letter:{normalized_fields['dead_letter_id']}"
    payload = {
        "event": event,
        "level": normalized_level,
        "ts": datetime.now(UTC).isoformat(),
        "event_version": 1,
        "service": service_name,
        **normalized_fields,
    }
    line = json.dumps(payload, default=str)
    if payload["level"] in {"error", "critical"}:
        logger.error(line)
    elif payload["level"] in {"warn", "warning"}:
        logger.warning(line)
    else:
        logger.info(line)
