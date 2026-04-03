from __future__ import annotations

import json
import logging

from app.core.telemetry import emit_diagnostic


def test_emit_diagnostic_logs_structured_payload(caplog):
    caplog.set_level(logging.INFO)
    emit_diagnostic("test_event", foo="bar")
    assert caplog.records
    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "test_event"
    assert payload["level"] == "info"
    assert payload["event_version"] == 1
    assert payload["foo"] == "bar"
    assert isinstance(payload["ts"], str)


def test_emit_diagnostic_warning_level_uses_warning_logger(caplog):
    caplog.set_level(logging.WARNING)
    emit_diagnostic("warn_event", level="warning", detail="degraded")
    assert caplog.records
    assert caplog.records[-1].levelname == "WARNING"
    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "warn_event"
    assert payload["level"] == "warning"
    assert payload["detail"] == "degraded"


def test_emit_diagnostic_normalizes_service_and_derives_correlation(caplog):
    caplog.set_level(logging.INFO)
    emit_diagnostic(
        "job_event",
        level="warn",
        service_name="api-worker-bridge",
        job_id="job-123",
    )
    payload = json.loads(caplog.records[-1].message)
    assert payload["service"] == "api-worker-bridge"
    assert payload["level"] == "warning"
    assert payload["job_id"] == "job-123"
    assert payload["correlation_id"] == "job:job-123"
