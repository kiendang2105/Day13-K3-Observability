from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import logging_config
from app.main import app

ENRICHMENT_FIELDS = {"user_id_hash", "session_id", "feature", "model", "env"}
CORRELATION_ID_FORMAT = re.compile(r"^req-[0-9a-f]{8}$")


def read_events(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def post_chat(client: TestClient, message: str, user_id: str = "student-01", **kwargs):
    return client.post(
        "/chat",
        json={
            "user_id": user_id,
            "session_id": "session-01",
            "feature": "qa",
            "message": message,
        },
        **kwargs,
    )


def test_generated_correlation_id_is_returned_and_logged(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = post_chat(client, "Explain observability")

    assert response.status_code == 200
    correlation_id = response.headers["x-request-id"]
    assert CORRELATION_ID_FORMAT.match(correlation_id)
    assert response.json()["correlation_id"] == correlation_id
    assert float(response.headers["x-response-time-ms"]) >= 0

    api_events = [e for e in read_events(log_path) if e.get("service") == "api"]
    assert api_events
    assert all(e["correlation_id"] == correlation_id for e in api_events)


def test_inbound_request_id_is_reused_and_rejected_when_unsafe(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        trusted = post_chat(client, "Explain observability", headers={"x-request-id": "gw-abc123"})
        spoofed = post_chat(client, "Explain observability", headers={"x-request-id": "bad id\nx: y"})

    assert trusted.headers["x-request-id"] == "gw-abc123"
    assert CORRELATION_ID_FORMAT.match(spoofed.headers["x-request-id"])


def test_each_request_gets_its_own_correlation_id(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        first = post_chat(client, "Explain observability")
        second = post_chat(client, "Explain tracing")

    assert first.headers["x-request-id"] != second.headers["x-request-id"]

    api_events = [e for e in read_events(log_path) if e.get("service") == "api"]
    assert len({e["correlation_id"] for e in api_events}) == 2


def test_api_events_carry_enrichment_context(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        post_chat(client, "Explain observability", user_id="student-42")

    api_events = [e for e in read_events(log_path) if e.get("service") == "api"]
    assert api_events
    for event in api_events:
        assert ENRICHMENT_FIELDS.issubset(event.keys())
        assert event["user_id_hash"] != "student-42"


def test_pii_never_reaches_the_log_file(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    message = "Email student@vinuni.edu.vn, phone 0901234567, card 4111 1111 1111 1111"

    with TestClient(app) as client:
        post_chat(client, message)

    raw = log_path.read_text(encoding="utf-8")
    assert "student@vinuni.edu.vn" not in raw
    assert "0901234567" not in raw
    assert "4111 1111 1111 1111" not in raw
    assert "REDACTED_EMAIL" in raw
