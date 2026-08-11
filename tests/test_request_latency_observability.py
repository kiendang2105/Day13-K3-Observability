from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import agent as agent_module
from app import logging_config
from app.main import app

PAYLOAD = {
    "user_id": "student-01",
    "session_id": "session-01",
    "feature": "qa",
    "message": "Explain observability",
}
DELAY = 0.3


def read_events(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_edge_access_log_captures_more_than_agent_latency(monkeypatch, tmp_path: Path) -> None:
    """request_completed phải bao trọn thời gian request, không chỉ phần agent.

    response_sent.latency_ms bắt đầu đếm từ lúc LabAgent.run chạy, nên nó không
    thấy khoảng request nằm chờ trước đó. Dưới sự cố rag_slow hai con số này lệch
    nhau 5 lần và dashboard đọc nhầm con số nhỏ.
    """
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post("/chat", json=PAYLOAD)

    events = read_events(log_path)
    completed = next(e for e in events if e["event"] == "request_completed")
    sent = next(e for e in events if e["event"] == "response_sent")

    assert completed["service"] == "http"
    assert completed["correlation_id"] == response.headers["x-request-id"]
    assert completed["payload"]["path"] == "/chat"
    assert completed["payload"]["status_code"] == 200
    assert completed["latency_ms"] >= sent["latency_ms"]


def test_health_check_is_also_access_logged(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        client.get("/health")

    paths = [
        e["payload"]["path"] for e in read_events(log_path) if e["event"] == "request_completed"
    ]
    assert "/health" in paths


def test_concurrent_requests_do_not_serialize(monkeypatch, tmp_path: Path) -> None:
    """Handler async không được giữ event loop khi gọi code đồng bộ chặn.

    Trước khi dùng run_in_threadpool, một retrieval chậm 2.5s làm 5 request đồng
    thời xếp hàng nối đuôi: client chờ 14 giây trong khi server chỉ ghi nhận 2.65s.
    """
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    def slow_retrieve(message: str) -> list[str]:
        time.sleep(DELAY)
        return ["doc"]

    monkeypatch.setattr(agent_module, "retrieve", slow_retrieve)

    async def send_three() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            responses = await asyncio.gather(*(client.post("/chat", json=PAYLOAD) for _ in range(3)))
            elapsed = time.perf_counter() - started
        assert all(r.status_code == 200 for r in responses)
        return elapsed

    elapsed = asyncio.run(send_three())

    # Nối đuôi nhau sẽ tốn >= 3 * DELAY. Chạy chồng lấn thì gần 1 * DELAY.
    assert elapsed < DELAY * 2.5, f"request đang bị xếp hàng: {elapsed:.2f}s cho 3 request"


def test_correlation_id_survives_the_threadpool_hop(monkeypatch, tmp_path: Path) -> None:
    """Đẩy agent sang worker thread không được làm mất context của request."""
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post("/chat", json=PAYLOAD)

    correlation_id = response.headers["x-request-id"]
    api_events = [e for e in read_events(log_path) if e.get("service") == "api"]
    assert api_events
    assert all(e["correlation_id"] == correlation_id for e in api_events)
    assert all("user_id_hash" in e for e in api_events)
