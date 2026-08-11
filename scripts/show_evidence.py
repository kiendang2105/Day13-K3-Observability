"""Dựng khung hình evidence cho Checkpoint 1 để chụp màn hình.

    python scripts/show_evidence.py correlation
    python scripts/show_evidence.py pii

Yêu cầu API đang chạy tại http://127.0.0.1:8000.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

BASE_URL = "http://127.0.0.1:8000"
LOG_PATH = Path("data/logs.jsonl")
WIDTH = 78

# Cùng bộ detector với scripts/validate_logs.py: quét PII độc lập với hàm scrub
# của app, nên kết quả 0 leak là bằng chứng kiểm chứng được chứ không tự khai.
PII_DETECTORS = {
    "email": re.compile(r"[\w.-]+@[\w.-]+\.\w+"),
    "phone_vn": re.compile(r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)"),
    "cccd": re.compile(r"\b\d{12}\b"),
    "credit_card": re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
}

CLEAN_MESSAGE = "How do metrics, traces and logs work together?"

# Chia nho theo tung cap PII: summarize_text cat preview o 80 ky tu, message dai
# se bi cat mat phan duoi va anh evidence khong thay du cac loai redaction.
PII_CASES = (
    "Email leduc@vinuni.edu.vn va SDT 0901234567",
    "The 4111 1111 1111 1111, CCCD 001203004567",
    "Ho chieu B1234567, nha o so 12, duong Lang Ha",
)


def banner(title: str) -> None:
    print()
    print("=" * WIDTH)
    print(f"  {title}")
    print("=" * WIDTH)


def section(title: str) -> None:
    print()
    print(f"--- {title} " + "-" * max(0, WIDTH - len(title) - 5))


def send(message: str) -> tuple[httpx.Response, dict]:
    payload = {
        "user_id": "evidence-user",
        "session_id": "evidence-session",
        "feature": "qa",
        "message": message,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{BASE_URL}/chat", json=payload)
    response.raise_for_status()
    return response, payload


def log_lines_for(correlation_id: str) -> list[dict]:
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("correlation_id") == correlation_id:
            records.append(record)
    return records


def show_correlation() -> None:
    response, payload = send(CLEAN_MESSAGE)
    correlation_id = response.json()["correlation_id"]

    banner("EVIDENCE 1 - Correlation ID xuyen suot mot request")

    section("1. Client gui request (khong kem x-request-id)")
    print(f"POST {BASE_URL}/chat")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    section("2. Response headers - server tra ID ve cho client")
    for header in ("x-request-id", "x-response-time-ms"):
        print(f"{header}: {response.headers[header]}")
    print(f"body.correlation_id: {correlation_id}")

    records = log_lines_for(correlation_id)
    section(f"3. Log lines mang cung correlation_id ({len(records)} dong)")
    for record in records:
        print(json.dumps(record, indent=2, ensure_ascii=False))

    section("Ket luan")
    print(f"Header, response body va {len(records)} log line deu dung 1 ID:")
    print(f"  {correlation_id}")
    print("=> Tu 1 ID nay truy nguoc duoc toan bo vong doi cua request.")
    print()


def show_pii() -> None:
    banner("EVIDENCE 2 - PII bi redact truoc khi ghi log")

    records: list[dict] = []
    correlation_ids: list[str] = []

    section("INPUT (client gui len)  ->  OUTPUT (thuc te trong data/logs.jsonl)")
    for message in PII_CASES:
        response, _ = send(message)
        correlation_id = response.json()["correlation_id"]
        correlation_ids.append(correlation_id)
        request_records = log_lines_for(correlation_id)
        records.extend(request_records)

        preview = next(
            (record.get("payload", {}).get("message_preview")
             for record in request_records
             if record.get("event") == "request_received"),
            "<khong tim thay log>",
        )
        print()
        print(f"  IN  | {message}")
        print(f"  OUT | {preview}")
        print(f"  ID  | {correlation_id}")

    section("Quet PII doc lap tren toan bo log line cua 3 request tren")
    raw = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    leaks = {name: d.findall(raw) for name, d in PII_DETECTORS.items() if d.search(raw)}
    for name in PII_DETECTORS:
        status = f"LEAK -> {leaks[name]}" if name in leaks else "sach"
        print(f"  {name:<12} {status}")

    section("Ket luan")
    print(f"So log line da quet: {len(records)} | So PII leak: {len(leaks)}")
    print("Bo detector tren lay tu scripts/validate_logs.py (doc lap voi app).")
    print("passport_vn va address_vn la pattern nhom tu them, ngoai bo cham.")
    print()
    print("=> PII bi thay bang [REDACTED_*] TRUOC khi JsonlFileProcessor ghi xuong")
    print("   dia, nen ban ghi tren dia khong con du lieu goc de khoi phuc.")
    print()


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("view", choices=["correlation", "pii"])
    args = parser.parse_args()

    if not LOG_PATH.exists():
        print(f"Error: {LOG_PATH} not found. Chay API va load_test truoc.")
        sys.exit(1)

    if args.view == "correlation":
        show_correlation()
    else:
        show_pii()


if __name__ == "__main__":
    main()
