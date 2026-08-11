"""Do khoang chenh giua latency client chiu va latency server ghi nhan.

    python scripts/probe_concurrency.py                 # dung input challenge
    python scripts/probe_concurrency.py --concurrency 8

Gui N request dong thoi roi doi chieu ba moc thoi gian cua cung mot request:

    client_ms  - client bam gio quanh loi goi HTTP, tuc la thu nguoi dung chiu
    header_ms  - x-response-time-ms do middleware do, tinh tu luc request vao
    agent_ms   - response_sent.latency_ms, chi tinh tu luc LabAgent.run bat dau

Khi ba con so nay lech nhau nhieu, phan chenh la thoi gian request nam cho ma
dashboard khong nhin thay. Dung script nay de tai lap ket qua o muc 6 cua
submission/REPORT.md: bat rag_slow roi chay truoc va sau khi bo run_in_threadpool
khoi app/main.py.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.challenge import load_challenge, ordered_queries
from app.cli import configure_utf8_stdio

BASE_URL = "http://127.0.0.1:8000"


def send(payload: dict) -> dict:
    started = time.perf_counter()
    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{BASE_URL}/chat", json=payload)
    client_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    body = response.json()
    return {
        "cid": body["correlation_id"],
        "client_ms": client_ms,
        "header_ms": float(response.headers["x-response-time-ms"]),
        "agent_ms": body["latency_ms"],
    }


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    payloads = ordered_queries(load_challenge())[: args.concurrency]
    while len(payloads) < args.concurrency:
        payloads.append(payloads[len(payloads) % max(1, len(payloads))])

    health = httpx.get(f"{BASE_URL}/health", timeout=10.0).json()
    print(f"incidents dang bat: {health['incidents']}")
    print(f"gui {len(payloads)} request dong thoi\n")

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(payloads)) as executor:
        results = list(executor.map(send, payloads))
    wall_ms = (time.perf_counter() - started) * 1000

    print(f"{'correlation_id':<16}{'client_ms':>11}{'header_ms':>11}{'agent_ms':>10}{'cho hang doi':>14}")
    for row in sorted(results, key=lambda r: r["client_ms"]):
        print(
            f"{row['cid']:<16}{row['client_ms']:>11.0f}{row['header_ms']:>11.0f}"
            f"{row['agent_ms']:>10}{row['client_ms'] - row['header_ms']:>14.0f}"
        )

    slowest_client = max(r["client_ms"] for r in results)
    slowest_agent = max(r["agent_ms"] for r in results)
    print(f"\nwall-clock ca lo        : {wall_ms:.0f} ms")
    print(f"agent_ms lon nhat       : {slowest_agent} ms   <- con so dashboard doc")
    print(f"client_ms lon nhat      : {slowest_client:.0f} ms   <- con so nguoi dung chiu")
    print(f"phan server khong ghi   : {slowest_client - slowest_agent:.0f} ms")
    if slowest_agent and slowest_client / slowest_agent > 2:
        print("\nCANH BAO: client chiu gap hon 2 lan con so server ghi nhan.")
        print("Request dang xep hang chu khong chay song song.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
