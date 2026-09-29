from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app
from app.pii import hash_user_id

REQUEST_ID_RE = re.compile(r"req-[0-9a-f]{8}")


def _post_chat(message: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                headers=headers or {},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": message,
                },
            )

    return asyncio.run(send_request())


def _read_events(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_generates_correlation_id_and_response_headers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post_chat("Explain observability")

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    assert REQUEST_ID_RE.fullmatch(request_id)
    assert response.json()["correlation_id"] == request_id
    assert float(response.headers["x-response-time-ms"]) >= 0


def test_reuses_valid_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post_chat("Explain observability", headers={"x-request-id": "req-abcdef12"})

    assert response.headers["x-request-id"] == "req-abcdef12"
    assert response.json()["correlation_id"] == "req-abcdef12"


def test_replaces_invalid_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    response = _post_chat("Explain observability", headers={"x-request-id": "student@vinuni.edu.vn"})

    request_id = response.headers["x-request-id"]
    assert request_id != "student@vinuni.edu.vn"
    assert REQUEST_ID_RE.fullmatch(request_id)


def test_each_request_gets_its_own_correlation_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    first = _post_chat("Explain observability")
    second = _post_chat("Explain observability")

    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_api_logs_are_enriched_and_scrubbed(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    response = _post_chat("My email is student@vinuni.edu.vn and phone 0987654321")

    api_events = [event for event in _read_events(log_path) if event.get("service") == "api"]
    assert {event["event"] for event in api_events} >= {"request_received", "response_sent"}
    for event in api_events:
        assert event["correlation_id"] == response.headers["x-request-id"]
        assert event["user_id_hash"] == hash_user_id("student-01")
        assert event["session_id"] == "session-01"
        assert event["feature"] == "qa"
        assert event["model"]
        assert event["env"]
        assert "student-01" not in json.dumps(event)

    raw_log = log_path.read_text(encoding="utf-8")
    assert "student@vinuni.edu.vn" not in raw_log
    assert "0987654321" not in raw_log
    assert "[REDACTED_EMAIL]" in raw_log
